# 🏠 Agente CEF — Monitor de Imóveis Automático

Monitora diariamente o CSV oficial da Caixa Econômica Federal,
filtra imóveis em **Cerquilho**, **Boituva** e **Tietê** (SP)
e envia alertas pelo **WhatsApp** quando aparecem novidades.

> **Custo: R$ 0,00** — roda 100% no GitHub Actions (gratuito).

---

## ⚙️ Configuração (único setup, ~10 minutos)

### 1. Criar o repositório no GitHub

1. Acesse [github.com](https://github.com) e crie uma conta gratuita (se não tiver)
2. Clique em **New repository**
3. Nome sugerido: `cef-monitor`
4. Marque **Public** (necessário para GitHub Pages gratuito)
5. Clique em **Create repository**

---

### 2. Subir os arquivos

Faça upload de todos os arquivos deste projeto para o repositório:

```
cef-monitor/
├── .github/
│   └── workflows/
│       └── monitor.yml       ← automação diária
├── scripts/
│   ├── filtrar.py            ← baixa e filtra o CSV
│   └── notificar.py          ← envia WhatsApp
└── docs/
    └── index.html            ← painel web
```

> Dica: no GitHub, use **Add file → Upload files** para enviar tudo de uma vez.

---

### 3. Ativar GitHub Pages (painel web)

1. No repositório, vá em **Settings → Pages**
2. Em **Source**, selecione `Deploy from a branch`
3. Branch: `main` | Pasta: `/docs`
4. Clique **Save**

Após ~2 minutos, seu painel estará disponível em:
`https://SEU_USUARIO.github.io/cef-monitor`

---

### 4. Configurar WhatsApp (CallMeBot — gratuito)

O agente usa o **CallMeBot** para enviar mensagens no seu WhatsApp pessoal.

**Ativar o bot:**
1. Salve o contato `+34 644 44 77 17` no seu celular como "CallMeBot"
2. Envie a mensagem: `I allow callmebot to send me messages`
3. Você receberá uma mensagem com sua **API Key** (ex: `1234567`)

**Adicionar ao GitHub:**
1. No repositório, vá em **Settings → Secrets and variables → Actions**
2. Clique em **New repository secret**
3. Adicione os dois secrets:

| Nome | Valor |
|------|-------|
| `WPP_PHONE` | Seu número com DDI: `5511999998888` |
| `WPP_APIKEY` | A chave recebida do CallMeBot: `1234567` |

---

### 5. Executar pela primeira vez

1. Vá em **Actions** no repositório
2. Clique em **Monitor Imóveis Caixa**
3. Clique em **Run workflow → Run workflow**

O agente vai rodar, filtrar o CSV e salvar os resultados.
A partir daí, **roda sozinho todo dia às 7h** (horário de Brasília).

---

## 📱 Usando o painel

Acesse `https://SEU_USUARIO.github.io/cef-monitor` no celular.

- Os dados são atualizados automaticamente toda manhã
- Imóveis novos aparecem destacados em verde com badge "NOVO"
- Botão **Enviar no WhatsApp** gera o resumo para compartilhar

---

## 🔧 Personalizar filtros

Edite o arquivo `scripts/filtrar.py`:

```python
CIDADES   = ['CERQUILHO', 'BOITUVA', 'TIETE']  # adicione outras cidades
TIPOS     = ['CASA', 'APARTAMENTO', 'APTO']      # ou remova tipos
VALOR_MAX = 150_000                              # altere o valor máximo
```

---

## ❓ Perguntas frequentes

**O agente funciona sem o WhatsApp configurado?**
Sim. O painel web funciona normalmente. O WhatsApp é opcional.

**Com que frequência o CSV da Caixa é atualizado?**
Diariamente, de segunda a sexta.

**O que acontece se o CSV mudar de formato?**
O `filtrar.py` usa mapeamento flexível de colunas. Mas se a Caixa
mudar drasticamente a estrutura, pode ser necessário ajustar o script.

**Posso adicionar mais cidades?**
Sim, edite a lista `CIDADES` no `filtrar.py`.
