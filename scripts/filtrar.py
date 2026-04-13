"""
filtrar.py
Baixa o CSV oficial da Caixa (SP), filtra imóveis por cidade/tipo/valor
e salva o resultado em docs/imoveis.json para ser exibido no painel web.
"""

import os
import json
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO

# ── CONFIG ─────────────────────────────────────────────────────────────────────
CIDADES    = ['CERQUILHO', 'BOITUVA', 'TIETE', 'TIETÊ']
TIPOS      = ['CASA', 'APARTAMENTO', 'APTO']
VALOR_MAX  = 200_000
CSV_URL    = 'https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_SP.csv'
OUT_JSON   = 'docs/imoveis.json'
OUT_TS     = 'docs/ultima_execucao.txt'
IDS_FILE   = 'docs/ids_anteriores.json'

# ── DOWNLOAD ───────────────────────────────────────────────────────────────────
def baixar_csv():
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    print(f"[{ts()}] Baixando CSV: {CSV_URL}")
    r = requests.get(CSV_URL, headers=headers, timeout=60)
    r.raise_for_status()
    print(f"[{ts()}] CSV recebido: {len(r.content):,} bytes | encoding: {r.encoding}")
    # CSV usa Windows-1252
    return r.content.decode('windows-1252', errors='replace')

# ── PARSE E FILTRO ─────────────────────────────────────────────────────────────
def processar(raw: str) -> list[dict]:
    # Detectar separador
    sep = ';' if ';' in raw.split('\n')[0] else ','
    df  = pd.read_csv(StringIO(raw), sep=sep, dtype=str, on_bad_lines='skip')

    print(f"[{ts()}] Colunas: {list(df.columns)}")
    print(f"[{ts()}] Total de linhas: {len(df):,}")

    # Normalizar nomes de colunas
    df.columns = (
        df.columns
          .str.strip()
          .str.upper()
          .str.normalize('NFD')
          .str.encode('ascii', errors='ignore')
          .str.decode('ascii')
          .str.replace(r'\s+', '_', regex=True)
    )

    # Mapear colunas com fallback
    def col(preferido, alternativas=[]):
        for nome in [preferido] + alternativas:
            matches = [c for c in df.columns if nome in c]
            if matches:
                return matches[0]
        return None

    C_CIDADE  = col('CIDADE', ['MUNICIPIO'])
    C_TIPO    = col('TIPO', ['DESCRICAO'])
    C_PRECO   = col('PRECO', ['VALOR_VENDA', 'VALOR_MINIMO'])
    C_AVAL    = col('AVALIACAO', ['VALOR_AVALIACAO'])
    C_LOGR    = col('LOGRADOURO', ['ENDERECO', 'RUA'])
    C_NUM     = col('NUMERO', ['NUM'])
    C_COMPL   = col('COMPLEMENTO', ['COMPL'])
    C_BAIRRO  = col('BAIRRO', ['BAIRRO'])
    C_UF      = col('UF', ['ESTADO'])
    C_MODAL   = col('MODALIDADE', ['TIPO_VENDA'])
    C_QUARTOS = col('QUARTOS', ['DORMITORIOS'])
    C_AREA    = col('AREA', ['AREA_PRIVATIVA', 'AREA_UTIL'])
    C_LINK    = col('LINK', ['URL', 'SITE'])
    C_FGTS    = col('FGTS', ['ACEITA_FGTS'])
    C_FINANC  = col('FINANCIAMENTO', ['ACEITA_FINANCIAMENTO'])
    C_ID      = col('N_IMOVEL', ['IMOVEL', 'ID', 'COD'])

    imoveis = []
    for _, row in df.iterrows():
        def g(c):
            return str(row[c]).strip() if c and c in df.columns else ''

        cidade_raw = g(C_CIDADE)
        cidade_norm = (
            cidade_raw.upper()
            .encode('ascii', errors='ignore').decode()
            .replace('TIETE', 'TIETE')
        )

        # Filtro cidade
        if cidade_norm not in ['CERQUILHO', 'BOITUVA', 'TIETE']:
            continue

        # Filtro tipo
        tipo_raw = (g(C_TIPO) + ' ' + g(C_LOGR)).upper()
        tipo_ok = any(t in tipo_raw for t in TIPOS)
        if not tipo_ok:
            continue

        # Filtro financiamento
        financ = g(C_FINANC).upper()
        if 'NAO' in financ or 'NÃO' in financ:
            continue

        # Filtro valor
        preco_raw = g(C_PRECO).replace('.', '').replace(',', '.').strip()
        try:
            preco = float(''.join(c for c in preco_raw if c.isdigit() or c == '.'))
        except ValueError:
            continue
        if preco <= 0 or preco > VALOR_MAX:
            continue
        print(f"[{ts()}] DEBUG: {cidade_raw} | {tipo_raw} | R${preco} | Financiamento: {financ}") #opção para depurar o erro
        
        # Avaliação e desconto
        aval_raw = g(C_AVAL).replace('.', '').replace(',', '.').strip()
        try:
            aval = float(''.join(c for c in aval_raw if c.isdigit() or c == '.'))
        except ValueError:
            aval = preco
        desconto = round((1 - preco / aval) * 100) if aval > preco else 0

        # Tipo normalizado
        tipo_norm = 'Casa' if 'CASA' in tipo_raw else 'Apartamento'

        # Endereço
        end_parts = [g(C_LOGR), g(C_NUM), g(C_COMPL)]
        endereco  = ', '.join(p for p in end_parts if p and p != 'nan')

        # ID
        imovel_id = g(C_ID) or f"{cidade_norm}_{_}"

        # Link
        link = g(C_LINK) if g(C_LINK) and g(C_LINK).startswith('http') else \
               f"https://venda-imoveis.caixa.gov.br/sistema/detalhe-imovel.asp?hdnOrigem=index&hdnimovel={imovel_id}"

        imoveis.append({
            'id':        imovel_id,
            'tipo':      tipo_norm,
            'endereco':  endereco,
            'bairro':    g(C_BAIRRO),
            'cidade':    cidade_raw,
            'uf':        g(C_UF) or 'SP',
            'preco':     preco,
            'avaliacao': aval,
            'desconto':  desconto,
            'modalidade': g(C_MODAL),
            'quartos':   g(C_QUARTOS),
            'area':      g(C_AREA),
            'fgts':      'NAO' not in g(C_FGTS).upper(),
            'link':      link,
        })

    return imoveis

# ── DETECTAR NOVOS ─────────────────────────────────────────────────────────────
def detectar_novos(imoveis: list[dict]) -> list[dict]:
    ids_ant = []
    if os.path.exists(IDS_FILE):
        with open(IDS_FILE) as f:
            ids_ant = json.load(f)

    ids_atuais = [i['id'] for i in imoveis]
    novos_ids  = set(ids_atuais) - set(ids_ant)

    os.makedirs('docs', exist_ok=True)
    with open(IDS_FILE, 'w') as f:
        json.dump(ids_atuais, f)

    return [i for i in imoveis if i['id'] in novos_ids]

# ── SALVAR ─────────────────────────────────────────────────────────────────────
def salvar(imoveis: list[dict], novos: list[dict]):
    os.makedirs('docs', exist_ok=True)
    agora = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')

    payload = {
        'gerado_em':    agora,
        'total':        len(imoveis),
        'novos':        len(novos),
        'novos_ids':    [i['id'] for i in novos],
        'imoveis':      imoveis,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(OUT_TS, 'w') as f:
        f.write(agora)

    print(f"[{ts()}] Salvo: {OUT_JSON} ({len(imoveis)} imóveis, {len(novos)} novos)")

    # Exportar para GitHub Actions
    with open(os.environ.get('GITHUB_ENV', '/dev/null'), 'a') as env:
        env.write(f"NOVOS_COUNT={len(novos)}\n")
        env.write(f"TOTAL_COUNT={len(imoveis)}\n")
        msgs = []
        for n in novos[:3]:
            msgs.append(f"{n['tipo']} em {n['cidade']} - {fmt_val(n['preco'])}")
        env.write(f"NOVOS_RESUMO={'|'.join(msgs)}\n")

def fmt_val(v):
    return f"R$ {v:,.0f}".replace(',', '.')

def ts():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M:%S')

# ── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f"[{ts()}] === Agente CEF iniciado ===")
    raw     = baixar_csv()
    imoveis = processar(raw)
    novos   = detectar_novos(imoveis)
    salvar(imoveis, novos)
    print(f"[{ts()}] === Concluído: {len(imoveis)} imóveis, {len(novos)} novos ===")
