"""
filtrar.py
Lê o CSV oficial da Caixa (SP), filtra imóveis por cidade/tipo/valor
e salva o resultado em docs/imoveis.json para ser exibido no painel web.

Estrutura real do CSV da Caixa (14/04/2026):
  [0] N° do imóvel  [1] UF  [2] Cidade    [3] Bairro      [4] Endereço
  [5] Preço         [6] Valor de avaliação [7] Desconto    [8] Financiamento
  [9] Descrição     [10] Modalidade de venda               [11] Link de acesso

  - Separador: ponto-e-vírgula (;)
  - Encoding:  Windows-1252
  - Linha 0:   título "Lista de Imóveis da Caixa;..."  ← pular
  - Linha 1:   cabeçalho real
  - Linha 2+:  dados
  - IDs longos aparecem em notação científica (ex: 8,7877E+12) — usar link para ID real
"""

import os
import json
import unicodedata
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ── CONFIG ─────────────────────────────────────────────────────────────────────
CIDADES   = ['CERQUILHO', 'BOITUVA', 'TIETE']
TIPOS     = ['CASA', 'APARTAMENTO']
VALOR_MAX = 200_000
CSV_URL   = 'https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_SP.csv'
OUT_JSON  = 'docs/imoveis.json'
OUT_TS    = 'docs/ultima_execucao.txt'
IDS_FILE  = 'docs/ids_anteriores.json'
DEBUG_LOG = 'docs/debug.log'

# Índices fixos das colunas (confirmados na inspeção do CSV real)
I_ID    = 0
I_UF    = 1
I_CID   = 2
I_BAIRRO= 3
I_END   = 4
I_PRECO = 5
I_AVAL  = 6
I_DESC_P= 7   # Desconto %
I_FINANC= 8
I_DESC  = 9   # Descrição (contém tipo + área + quartos)
I_MODAL = 10
I_LINK  = 11

# ── HELPERS ────────────────────────────────────────────────────────────────────
def ts():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M:%S')

def agora_br():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')

def fmt_val(v):
    return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def remover_acentos(texto: str) -> str:
    return (
        unicodedata.normalize('NFD', texto)
        .encode('ascii', errors='ignore')
        .decode()
        .strip()
    )

def parse_valor(texto: str) -> float:
    """Converte '75.305,50' → 75305.50  |  '8,7877E+12' → 0 (inválido para preço)"""
    try:
        limpo = texto.replace('.', '').replace(',', '.').strip()
        v = float(limpo)
        return v if v < 1_000_000_000 else 0.0   # ignora notação científica
    except (ValueError, AttributeError):
        return 0.0

def extrair_id_do_link(link: str) -> str:
    """Extrai o ID real do link: ...?hdnimovel=8787702405225 → '8787702405225'"""
    if 'hdnimovel=' in link:
        return link.split('hdnimovel=')[-1].strip()
    return ''

# ── DOWNLOAD ───────────────────────────────────────────────────────────────────
def baixar_csv() -> str:
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
    """
    Lê o CSV linha a linha (sem pandas) para evitar problemas de
    detecção de separador, cabeçalho duplo e IDs em notação científica.
    """
    # Criar pasta docs/ ANTES de qualquer operação de log
    os.makedirs('docs', exist_ok=True)

    linhas = raw.replace('\r', '').split('\n')
    total_linhas = len([l for l in linhas if l.strip()])
    print(f"[{ts()}] Total de linhas no CSV: {total_linhas:,}")
    print(f"[{ts()}] Header: {linhas[1][:80]}...")

    imoveis     = []
    descartados = []
    total_cidades = 0

    # Dados começam na linha 2 (linha 0 = título, linha 1 = cabeçalho)
    for num_linha, linha in enumerate(linhas[2:], start=3):
        if not linha.strip():
            continue

        cols = [c.strip() for c in linha.split(';')]
        if len(cols) < 10:
            continue

        def g(i):
            return cols[i].strip() if i < len(cols) else ''

        # ── FILTRO 1: CIDADE ──────────────────────────────────────────────────
        cidade_raw  = g(I_CID)
        cidade_norm = remover_acentos(cidade_raw.upper())

        if not any(c in cidade_norm for c in CIDADES):
            continue
        total_cidades += 1

        # ── FILTRO 2: TIPO (coluna Descrição) ─────────────────────────────────
        # Formato: "Apartamento, 46.95 de área total, 26.37 de área privativa..."
        # ou:      "Casa, 237.86 de área total, 44.10 de área privativa..."
        descricao   = g(I_DESC)
        desc_upper  = remover_acentos(descricao.upper())
        tipo_match  = next((t for t in TIPOS if desc_upper.startswith(t)), None)

        if not tipo_match:
            descartados.append(
                f"TIPO | L{num_linha} | {cidade_raw} | desc='{descricao[:40]}'"
            )
            continue

        # ── FILTRO 3: VALOR ───────────────────────────────────────────────────
        preco = parse_valor(g(I_PRECO))
        if preco <= 0:
            descartados.append(
                f"VALOR_INVALIDO | L{num_linha} | {cidade_raw} | raw='{g(I_PRECO)}'"
            )
            continue
        if preco > VALOR_MAX:
            descartados.append(
                f"VALOR_FORA | L{num_linha} | {cidade_raw} | {fmt_val(preco)}"
            )
            continue

        # ── PASSOU EM TODOS OS FILTROS ────────────────────────────────────────
        aval     = parse_valor(g(I_AVAL)) or preco
        desconto = round((1 - preco / aval) * 100) if aval > preco else 0

        tipo_norm = 'Casa' if tipo_match == 'CASA' else 'Apartamento'

        # ID real está no link (ID na coluna pode vir como notação científica)
        link      = g(I_LINK)
        imovel_id = extrair_id_do_link(link) or g(I_ID)

        # Extrair área privativa da descrição
        # Formato: "Casa, 237.86 de área total, 44.10 de área privativa, ..."
        area_privativa = ''
        area_total     = ''
        quartos        = ''
        try:
            partes = descricao.split(',')
            if len(partes) >= 2:
                area_total     = partes[1].strip().split(' ')[0] + ' m²'
            if len(partes) >= 3:
                area_privativa = partes[2].strip().split(' ')[0] + ' m²'
            for p in partes:
                if 'qto' in p.lower():
                    quartos = p.strip().split(' ')[0]
        except Exception:
            pass

        msg = (
            f"[{ts()}] ✅ APROVADO | {cidade_raw} | {tipo_norm} | "
            f"{fmt_val(preco)} | {g(I_FINANC)}"
        )
        print(msg)

        imoveis.append({
            'id':            imovel_id,
            'tipo':          tipo_norm,
            'endereco':      g(I_END),
            'bairro':        g(I_BAIRRO),
            'cidade':        cidade_raw,
            'uf':            g(I_UF) or 'SP',
            'preco':         preco,
            'avaliacao':     aval,
            'desconto':      desconto,
            'financiamento': g(I_FINANC),
            'modalidade':    g(I_MODAL),
            'area_total':    area_total,
            'area_privativa':area_privativa,
            'quartos':       quartos,
            'descricao':     descricao,
            'link':          link,
        })

    # ── GRAVAR DEBUG.LOG ──────────────────────────────────────────────────────
    with open(DEBUG_LOG, 'w', encoding='utf-8') as log:
        log.write(f"=== Execução: {agora_br()} ===\n")
        log.write(f"Total de linhas no CSV:      {total_linhas}\n")
        log.write(f"Registros nas cidades-alvo:  {total_cidades}\n")
        log.write(f"Aprovados:                   {len(imoveis)}\n")
        log.write(f"Descartados:                 {len(descartados)}\n")
        log.write(f"\n{'─'*60}\n")
        log.write("APROVADOS:\n")
        for im in imoveis:
            log.write(
                f"  {im['id']:20} | {im['tipo']:12} | {im['cidade']:12} | "
                f"{fmt_val(im['preco']):>15} | financ={im['financiamento']}\n"
            )
        log.write(f"\n{'─'*60}\n")
        log.write("DESCARTADOS (motivo | linha | cidade | detalhe):\n")
        for d in descartados:
            log.write(f"  {d}\n")

    print(f"[{ts()}] debug.log gravado: {len(imoveis)} aprovados, {len(descartados)} descartados")
    return imoveis

# ── DETECTAR NOVOS ─────────────────────────────────────────────────────────────
def detectar_novos(imoveis: list[dict]) -> list[dict]:
    ids_ant = []
    if os.path.exists(IDS_FILE):
        with open(IDS_FILE, encoding='utf-8') as f:
            ids_ant = json.load(f)

    ids_atuais = [i['id'] for i in imoveis]
    novos_ids  = set(ids_atuais) - set(ids_ant)

    with open(IDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ids_atuais, f)

    return [i for i in imoveis if i['id'] in novos_ids]

# ── SALVAR JSON ───────────────────────────────────────────────────────────────
def salvar(imoveis: list[dict], novos: list[dict]):
    payload = {
        'gerado_em': agora_br(),
        'total':     len(imoveis),
        'novos':     len(novos),
        'novos_ids': [i['id'] for i in novos],
        'imoveis':   imoveis,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(OUT_TS, 'w', encoding='utf-8') as f:
        f.write(agora_br())

    print(f"[{ts()}] Salvo: {OUT_JSON} ({len(imoveis)} imóveis, {len(novos)} novos)")

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
    print(f"[{ts()}] === Concluído: {len(imoveis)} imóveis, {len(novos)} novos ===")

    
