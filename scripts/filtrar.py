"""
filtrar.py
Baixa o CSV oficial da Caixa (SP), filtra imóveis por cidade/tipo/valor
e salva o resultado em docs/imoveis.json para ser exibido no painel web.
"""

import os
import json
import unicodedata
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO

# ── CONFIG ─────────────────────────────────────────────────────────────────────
CIDADES    = ['CERQUILHO', 'BOITUVA', 'TIETE']
TIPOS      = ['CASA', 'APARTAMENTO', 'APTO']
VALOR_MAX  = 200_000
CSV_URL    = 'https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_SP.csv'
OUT_JSON   = 'docs/imoveis.json'
OUT_TS     = 'docs/ultima_execucao.txt'
IDS_FILE   = 'docs/ids_anteriores.json'
DEBUG_LOG  = 'docs/debug.log'

# ── HELPERS ────────────────────────────────────────────────────────────────────
def ts():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M:%S')

def fmt_val(v):
    return f"R$ {v:,.0f}".replace(',', '.')

def remover_acentos(texto: str) -> str:
    """Remove acentos corretamente: TIETÊ → TIETE, CERQUILHO → CERQUILHO"""
    return (
        unicodedata.normalize('NFD', texto)
        .encode('ascii', errors='ignore')
        .decode()
        .strip()
    )

# ── DOWNLOAD ───────────────────────────────────────────────────────────────────
def baixar_csv():
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp',
        'Accept':  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    print(f"[{ts()}] Baixando CSV: {CSV_URL}")
    r = requests.get(CSV_URL, headers=headers, timeout=60)
    r.raise_for_status()
    print(f"[{ts()}] CSV recebido: {len(r.content):,} bytes")
    return r.content.decode('windows-1252', errors='replace')

# ── PARSE E FILTRO ─────────────────────────────────────────────────────────────
def processar(raw: str) -> list[dict]:

    sep = ';' if ';' in raw.split('\n')[0] else ','
    df  = pd.read_csv(StringIO(raw), sep=sep, dtype=str, on_bad_lines='skip')

    print(f"[{ts()}] Colunas originais: {list(df.columns)}")
    print(f"[{ts()}] Total de linhas no CSV: {len(df):,}")

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
    print(f"[{ts()}] Colunas normalizadas: {list(df.columns)}")

    def col(preferido, alternativas=[]):
        for nome in [preferido] + alternativas:
            matches = [c for c in df.columns if nome in c]
            if matches:
                return matches[0]
        return None

    # CORRIGIDO: TIPO_IMOVEL tem prioridade sobre TIPO genérico
    C_CIDADE  = col('CIDADE',               ['MUNICIPIO'])
    C_TIPO    = col('TIPO_IMOVEL',          ['TIPO', 'DESCRICAO'])
    C_PRECO   = col('PRECO',                ['VALOR_VENDA', 'VALOR_MINIMO'])
    C_AVAL    = col('VALOR_AVALIACAO',      ['AVALIACAO'])
    C_LOGR    = col('LOGRADOURO',           ['ENDERECO', 'RUA'])
    C_NUM     = col('NUMERO',               ['NUM'])
    C_COMPL   = col('COMPLEMENTO',          ['COMPL'])
    C_BAIRRO  = col('BAIRRO',               [])
    C_UF      = col('UF',                   ['ESTADO'])
    C_MODAL   = col('MODALIDADE',           ['TIPO_VENDA'])
    C_QUARTOS = col('QUARTOS',              ['DORMITORIOS'])
    C_AREA    = col('AREA_PRIVATIVA',       ['AREA_UTIL', 'AREA'])
    C_LINK    = col('LINK_DETALHE',         ['LINK', 'URL', 'SITE'])
    C_FGTS    = col('ACEITA_FGTS',          ['FGTS'])
    C_FINANC  = col('ACEITA_FINANCIAMENTO', ['FINANCIAMENTO'])
    C_ID      = col('N_IMOVEL',             ['IMOVEL', 'ID', 'COD'])

    print(f"[{ts()}] Mapeamento de colunas:")
    for nome, val in [('CIDADE', C_CIDADE), ('TIPO', C_TIPO), ('PRECO', C_PRECO),
                      ('FINANCIAMENTO', C_FINANC), ('ID', C_ID)]:
        print(f"           {nome:15} -> {val or 'NAO ENCONTRADA !'}")

    # CORRIGIDO: criar docs/ ANTES do loop para o debug.log funcionar
    os.makedirs('docs', exist_ok=True)

    imoveis     = []
    descartados = []

    for idx, row in df.iterrows():

        def g(c):
            return str(row[c]).strip() if c and c in df.columns else ''

        # FILTRO 1: CIDADE
        cidade_raw  = g(C_CIDADE)
        cidade_norm = remover_acentos(cidade_raw.upper())  # TIETÊ → TIETE

        if not any(c in cidade_norm for c in CIDADES):
            continue

        # FILTRO 2: TIPO
        tipo_col = remover_acentos(g(C_TIPO).upper())
        tipo_ok  = any(t in tipo_col for t in TIPOS)

        if not tipo_ok:
            descartados.append(f"TIPO | {cidade_raw} | tipo='{g(C_TIPO)}'")
            continue

        # FILTRO 3: FINANCIAMENTO
        #financ_raw  = g(C_FINANC)
        #financ_norm = remover_acentos(financ_raw.upper())
        # CORRIGIDO: bloqueia só quando explicitamente NAO sem SIM junto
        #if 'NAO' in financ_norm and 'SIM' not in financ_norm:
        #    descartados.append(f"FINANC | {cidade_raw} | financ='{financ_raw}'")
        #    continue

        # FILTRO 4: VALOR
        preco_raw = g(C_PRECO).replace('.', '').replace(',', '.').strip()
        try:
            preco = float(''.join(c for c in preco_raw if c.isdigit() or c == '.'))
        except ValueError:
            descartados.append(f"VALOR_INVALIDO | {cidade_raw} | preco='{g(C_PRECO)}'")
            continue

        if preco <= 0 or preco > VALOR_MAX:
            descartados.append(f"VALOR_FORA | {cidade_raw} | preco={preco}")
            continue

        # PASSOU EM TODOS OS FILTROS
        debug_msg = (
            f"[{ts()}] OK | {cidade_raw} | {tipo_col} | "
            f"{fmt_val(preco)} | financ='{financ_raw}'"
        )
        print(debug_msg)

        aval_raw = g(C_AVAL).replace('.', '').replace(',', '.').strip()
        try:
            aval = float(''.join(c for c in aval_raw if c.isdigit() or c == '.'))
        except ValueError:
            aval = preco
        desconto = round((1 - preco / aval) * 100) if aval > preco else 0

        tipo_norm = 'Casa' if 'CASA' in tipo_col else 'Apartamento'

        end_parts = [g(C_LOGR), g(C_NUM), g(C_COMPL)]
        endereco  = ', '.join(p for p in end_parts if p and p not in ('', 'nan'))

        imovel_id = g(C_ID) or f"{cidade_norm}_{idx}"

        link_val = g(C_LINK)
        link = link_val if link_val.startswith('http') else \
               f"https://venda-imoveis.caixa.gov.br/sistema/detalhe-imovel.asp?hdnOrigem=index&hdnimovel={imovel_id}"

        imoveis.append({
            'id':         imovel_id,
            'tipo':       tipo_norm,
            'endereco':   endereco,
            'bairro':     g(C_BAIRRO),
            'cidade':     cidade_raw,
            'uf':         g(C_UF) or 'SP',
            'preco':      preco,
            'avaliacao':  aval,
            'desconto':   desconto,
            'modalidade': g(C_MODAL),
            'quartos':    g(C_QUARTOS),
            'area':       g(C_AREA),
            'fgts':       'NAO' not in remover_acentos(g(C_FGTS).upper()),
            'link':       link,
        })

    # Gravar debug.log com aprovados + descartados por motivo
    with open(DEBUG_LOG, 'w', encoding='utf-8') as log:
        agora_str = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')
        log.write(f"=== Execucao: {agora_str} ===\n")
        log.write(f"Total no CSV: {len(df)}\n")
        log.write(f"Aprovados:   {len(imoveis)}\n")
        log.write(f"Descartados: {len(descartados)}\n\n")
        log.write("── APROVADOS ──\n")
        for im in imoveis:
            log.write(f"  {im['id']} | {im['tipo']} | {im['cidade']} | {fmt_val(im['preco'])}\n")
        log.write("\n── DESCARTADOS (motivo | cidade | detalhe) ──\n")
        for d in descartados:
            log.write(f"  {d}\n")

    print(f"[{ts()}] debug.log gravado: {len(imoveis)} aprovados, {len(descartados)} descartados")
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
        'gerado_em': agora,
        'total':     len(imoveis),
        'novos':     len(novos),
        'novos_ids': [i['id'] for i in novos],
        'imoveis':   imoveis,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(OUT_TS, 'w') as f:
        f.write(agora)

    print(f"[{ts()}] Salvo: {OUT_JSON} ({len(imoveis)} imoveis, {len(novos)} novos)")

    with open(os.environ.get('GITHUB_ENV', '/dev/null'), 'a') as env:
        env.write(f"NOVOS_COUNT={len(novos)}\n")
        env.write(f"TOTAL_COUNT={len(imoveis)}\n")
        msgs = [f"{n['tipo']} em {n['cidade']} - {fmt_val(n['preco'])}" for n in novos[:3]]
        env.write(f"NOVOS_RESUMO={'|'.join(msgs)}\n")

# ── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f"[{ts()}] === Agente CEF iniciado ===")
    raw     = baixar_csv()
    imoveis = processar(raw)
    novos   = detectar_novos(imoveis)
    salvar(imoveis, novos)
    print(f"[{ts()}] === Concluido: {len(imoveis)} imoveis, {len(novos)} novos ===")
    
