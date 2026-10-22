# MCP do PostgreSQL (bi_cometa)

Servidor MCP **somente leitura** que dá a um cliente MCP (Claude Code, Claude Desktop) acesso ao
banco do BI_COMETA, usando `docs/DATA_DICTIONARY.md` como documentação das tabelas.

| Item | O que faz |
|---|---|
| tool `listar_tabelas` | tabelas + fonte, estratégia de carga, job e nº aproximado de linhas |
| tool `descrever_tabela` | colunas reais do banco + seção do dicionário daquela tabela |
| tool `consultar_sql` | `SELECT`/`WITH` em transação read-only, timeout de 15s, limite de 200 linhas (máx. 1000) |
| resource `dicionario://bi_cometa` | o `DATA_DICTIONARY.md` completo |

## Instalação

```powershell
cd BI_COMETA\mcp_server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Uso local (stdio + túnel SSH)

O Postgres roda em container na VPS, e o compose publica a porta só em loopback
(`127.0.0.1:5434:5432`). Por isso o acesso é por **túnel SSH**, que precisa estar aberto enquanto
o MCP é usado:

```powershell
ssh -N -L 5434:127.0.0.1:5434 root@72.61.62.17
```

O servidor usa `MCP_DB_URL` se existir, senão `DB_URL` do `BI_COMETA/.env`. O `DB_URL` do `.env`
aponta para `localhost:5432` (ETL local) e **não serve** para o MCP; defina `MCP_DB_URL` (o `.env` é
ignorado pelo git, e o `Settings` do app ignora variáveis extras):

```
MCP_DB_URL=postgresql://bi_mcp:<senha>@127.0.0.1:5434/bi_cometa
```

Crie um role só com `SELECT` para o MCP (rodar na VPS como `bi_user`):

```sql
CREATE ROLE bi_mcp LOGIN PASSWORD '<senha forte>';
ALTER ROLE bi_mcp SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE bi_cometa TO bi_mcp;
GRANT USAGE ON SCHEMA public TO bi_mcp;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bi_mcp;
ALTER DEFAULT PRIVILEGES FOR ROLE bi_user IN SCHEMA public GRANT SELECT ON TABLES TO bi_mcp;
```

Registrar no Claude Code (o túnel precisa estar aberto):

```powershell
claude mcp add bi-cometa-postgres -- "<caminho>\BI_COMETA\mcp_server\.venv\Scripts\python.exe" "<caminho>\BI_COMETA\mcp_server\server.py"
```

## Na VPS (HTTPS, sem túnel)

O container `bi_cometa_mcp` roda na rede do BI (fala com `bi_cometa_db:5432`) e é publicado em
`https://infovale.valemilk.com.br/mcp` pelo nginx do Rebaixa (location `/mcp`). Cada chamada exige
`Authorization: Bearer <token>`; os tokens ficam em `MCP_AUTH_TOKENS=nome:token,...` e o `nome` aparece no
log de cada `consultar_sql`. Está em compose separado (`docker/docker-compose.mcp.yml`) para um erro de
build do MCP não travar o deploy da API/ETL.

```bash
cd /home/jefferson_pwr/BI_COMETA && git pull origin main

# 1) variáveis no .env da VPS (o token é gerado lá e não passa por chat/commit)
printf '\nMCP_DB_URL=postgresql://bi_mcp:SENHA@bi_cometa_db:5432/bi_cometa\n' >> .env
printf 'MCP_AUTH_TOKENS=admin:%s\n' "$(openssl rand -hex 32)" >> .env

# 2) rede dedicada (só o MCP e o nginx do Rebaixa) e subida do container
docker network create bi_cometa_mcp_net
docker-compose -f docker/docker-compose.mcp.yml --env-file .env up -d --build
docker logs bi_cometa_mcp --tail 20

# 3) no Rebaixa: recria o nginx (entra na rede nova) e recarrega
cd <pasta do rebaixa-app> && docker compose up -d && docker compose exec -T nginx nginx -s reload
```

Teste (sem token deve dar 401; com token e o corpo de `initialize`, 200):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://infovale.valemilk.com.br/mcp
```

Registrar no Claude Code (a partir de qualquer pasta, sem túnel):

```powershell
claude mcp add --transport http --scope user bi-cometa https://infovale.valemilk.com.br/mcp --header "Authorization: Bearer <token>"
```

Para revogar alguém, tire o token de `MCP_AUTH_TOKENS` e rode o `up -d` de novo. O modo HTTP se recusa a
subir sem tokens (ou com token de menos de 24 caracteres).

## Conector do Claude (OAuth, login pelo Rebaixa)

A tela **Settings → Connectors → Add custom connector** do Claude só pede nome e URL, então o token fixo não
serve. Com `MCP_PUBLIC_URL` definido (o compose já usa `https://infovale.valemilk.com.br`), o MCP também é um
servidor OAuth 2.1 (código + PKCE, registro dinâmico): ao conectar, o Claude abre `/mcp-login`, a pessoa entra
com e-mail e senha do **Rebaixa** e autoriza. O Claude Code e o `mcp-remote` seguem com o token fixo.

Variáveis (no `.env` da raiz do BI_COMETA, na VPS):

| Variável | Para quê |
|---|---|
| `MCP_OAUTH_ALLOWED_EMAILS` | **Obrigatória.** E-mails (separados por vírgula) que podem entrar. Tirar um e-mail daqui e recriar o container corta o acesso dele na hora, inclusive tokens já emitidos. |
| `MCP_OAUTH_ALLOWED_ROLES` | Perfis do Rebaixa aceitos (padrão `admin`). |
| `MCP_PUBLIC_URL` | URL pública, usada como emissor OAuth (padrão no compose: `https://infovale.valemilk.com.br`). |
| `MCP_OAUTH_LOGIN_URL` | Login do Rebaixa (padrão `http://rebaixa-backend:4000/api/auth/login`, pela rede do BI). |
| `MCP_OAUTH_REDIRECT_URIS` | Callbacks aceitos no registro (padrão: os do `claude.ai` e `claude.com`). |

Como funciona e o que protege:
- Só passa quem está na lista de e-mails, autentica no Rebaixa **e** tem perfil permitido. A senha só é
  repassada ao Rebaixa; nunca é gravada nem logada.
- Códigos e tokens são opacos, guardados só como hash no SQLite (`/data/oauth.db`, volume
  `mcp_oauth_data`, então sobrevivem a deploys). Access token dura 1h; refresh dura 30 dias e é rotacionado.
- O registro dinâmico só aceita os callbacks do Claude; qualquer outro `redirect_uri` é recusado.
- Limite de tentativas de login: 5 falhas por e-mail, 10 por IP e 40 no total, em 15 minutos.
- O log mostra o e-mail em cada login e em cada `consultar_sql` (`usuario=...`).
- Limitação do SDK: a rota `/revoke` exige o campo `client_secret` (mesmo vazio); para cortar alguém, use a
  lista de e-mails acima.

No Claude: **Settings → Connectors → Add custom connector**, nome `BI Cometa`, URL
`https://infovale.valemilk.com.br/mcp`, **Add** → **Connect** → entre com o e-mail e a senha do Rebaixa.

## Segurança

- Toda sessão abre com `default_transaction_read_only=on`; um `WITH ... DELETE` passa na checagem
  de prefixo, mas o Postgres recusa a escrita.
- A checagem de `SELECT`/`WITH` e de instrução única é só uma primeira barreira; a proteção real é
  a sessão read-only (e o role restrito, se configurado).
- Nada é escrito em stdout além do protocolo MCP; logs vão para stderr.
