"""
notificar.py
Envia alerta no WhatsApp via CallMeBot (gratuito, sem app instalado).
Só é chamado quando NOVOS_COUNT > 0.

Configuração (adicionar como Secrets no GitHub):
  WPP_PHONE  → seu número com DDI: 5511999998888
  WPP_APIKEY → chave gerada no callmebot.com/whatsapp.php
"""

import os
import json
import requests
from datetime import datetime
from urllib.parse import quote

# ── CONFIG ─────────────────────────────────────────────────────────────────────
WPP_PHONE  = os.environ.get('WPP_PHONE', '')
WPP_APIKEY = os.environ.get('WPP_APIKEY', '')
NOVOS_COUNT = int(os.environ.get('NOVOS_COUNT', '0'))
OUT_JSON    = 'docs/imoveis.json'

# ── MONTAR MENSAGEM ────────────────────────────────────────────────────────────
def montar_mensagem() -> str:
    with open(OUT_JSON, encoding='utf-8') as f:
        data = json.load(f)

    agora   = datetime.now().strftime('%d/%m/%Y %H:%M')
    novos   = [i for i in data['imoveis'] if i['id'] in data.get('novos_ids', [])]
    total   = data['total']

    linhas = [
        f"🏠 AGENTE IMÓVEIS CAIXA",
        f"📅 {agora}",
        f"📍 Cerquilho · Boituva · Tietê",
        f"",
    ]

    if novos:
        linhas.append(f"🔔 {len(novos)} NOVO(S) IMÓVEL(IS):")
        linhas.append("")
        for im in novos[:5]:   # máx 5 na mensagem
            preco = f"R$ {im['preco']:,.0f}".replace(',', '.')
            desc  = f" (-{im['desconto']}%)" if im['desconto'] > 0 else ""
            linhas += [
                f"✅ {im['tipo']} — {im['cidade']}/SP",
                f"📍 {im['endereco'] or 'Endereço no edital'}",
                f"💰 {preco}{desc}",
                f"🏷 {im['modalidade']}",
                f"🔗 {im['link']}",
                "",
            ]
        if len(novos) > 5:
            linhas.append(f"... e mais {len(novos)-5} imóvel(is). Veja o painel completo.")
            linhas.append("")

    linhas += [
        f"📊 Total na região: {total} imóveis",
        f"_Agente CEF · automático_",
    ]

    return '\n'.join(linhas)

# ── ENVIAR ─────────────────────────────────────────────────────────────────────
def enviar(msg: str):
    if not WPP_PHONE or not WPP_APIKEY:
        print("[WARN] WPP_PHONE ou WPP_APIKEY não configurados. Pulando notificação.")
        print("       Configure os Secrets no GitHub conforme o README.")
        return

    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WPP_PHONE}"
        f"&text={quote(msg)}"
        f"&apikey={WPP_APIKEY}"
    )
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        print("[OK] Notificação WhatsApp enviada com sucesso.")
    else:
        print(f"[WARN] Resposta CallMeBot: {r.status_code} — {r.text[:200]}")

# ── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if NOVOS_COUNT == 0:
        print("[INFO] Sem novidades. Notificação não enviada.")
    else:
        msg = montar_mensagem()
        print("── Mensagem a enviar ──")
        print(msg)
        print("──────────────────────")
        enviar(msg)
