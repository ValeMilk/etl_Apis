# 🔧 Configuração de Ambiente (.env)

## Resumo

| Cenário | DB_HOST | Comando |
|---------|---------|---------|
| **Local (PostgreSQL rodando local)** | `localhost` | `python src/main.py` |
| **Docker Compose (container)** | `bi_cometa_db` | `docker-compose up` |
| **Produção (VPS)** | `bi_cometa_db` | `docker-compose up` |

---

## 1️⃣ Executar LOCAL (sem Docker)

**Prerequisitos:**
- PostgreSQL 15 rodando em `localhost:5432`
- Python 3.10+ instalado
- `pip install -r requirements.txt`

**.env:**
```bash
DB_URL=postgresql+psycopg2://bi_user:bi_password@localhost:5432/bi_cometa
DATABASE_ECHO=false

API_BASE_URL=https://vendas.cometasupermercados.com.br
API_EMAIL=comercial@valemilk.com.br
API_PASSWORD=nbN'08D7G4)g
TOKEN_REFRESH_HOURS=12
VERIFY_SSL=false
REQUEST_TIMEOUT=30

VALEFISH_API_EMAIL=patricionogueira@valemilk.com.br
VALEFISH_API_PASSWORD=tR6{80#d,=Ku

LOG_LEVEL=INFO
ETL_INTERVAL_MINUTES=5

APP_HOST=0.0.0.0
APP_PORT=8000

API_AUTH_TOKEN=seu-token-aqui
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

**Executar:**
```bash
cd c:\Users\LENOVO\ 059\Desktop\ETL\ API\BI_COMETA
python src/main.py
```

---

## 2️⃣ Executar em DOCKER (local ou VPS)

**.env:**
```bash
# Mude apenas o HOST
DB_URL=postgresql+psycopg2://bi_user:bi_password@bi_cometa_db:5432/bi_cometa
# Resto igual ao acima
```

**Executar:**
```bash
cd /path/to/BI_COMETA  # ou c:\... no Windows
docker-compose -f docker/docker-compose.yml up -d
```

---

## 3️⃣ Variáveis Críticas

| Variável | Valor | Onde usar |
|----------|-------|-----------|
| `DB_HOST` | `localhost` \| `bi_cometa_db` | Sempre (local vs Docker) |
| `API_EMAIL` | `comercial@valemilk.com.br` | API Cometa |
| `API_PASSWORD` | `nbN'08D7G4)g` | API Cometa |
| `VALEFISH_API_EMAIL` | `patricionogueira@valemilk.com.br` | API Cometa (ValeFish) |
| `VALEFISH_API_PASSWORD` | `tR6{80#d,=Ku` | API Cometa (ValeFish) |
| `ETL_INTERVAL_MINUTES` | `5` | Frequência de execução |
| `TOKEN_REFRESH_HOURS` | `12` | Auto-refresh de token |

---

## ⚠️ Troubleshooting

**Erro: "could not connect to server: Connection refused"**
- ❌ Você configurou `localhost` mas o PG está em Docker
- ✅ Solução: Use `bi_cometa_db` se está em Docker

**Erro: "Name or service not known"**
- ❌ Você configurou `bi_cometa_db` mas rodar local
- ✅ Solução: Use `localhost` se está rodando fora do Docker

**Erro: "SCRAM authentication failed"**
- ❌ Credenciais `bi_user` / `bi_password` erradas
- ✅ Solução: Verificar no `docker-compose.yml` ou arquivo de backup

---

## 📝 Copiar .env.example

```bash
cp .env.example .env
# Depois editar conforme seu cenário (local ou Docker)
```
