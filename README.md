# BI_COMETA - Defensive ETL System

## 🎯 Visão Geral

**BI_COMETA** é um sistema de integração de dados (ETL) com **validação defensiva em 5 camadas**, que:

1. 🔄 **Extrai** vendas e estoque da API Cometa (cada 5 minutos)
2. 🛡️ **Valida** dados em múltiplas camadas (defensive programming)
3. 📊 **Estoura** estruturas complexas para formato tabular
4. 💾 **Armazena** em PostgreSQL para análise
5. 📈 **Expõe** dados via REST API (FastAPI)

```
┌─────────────────────────────────────────────────────┐
│           BI_COMETA v2.1 (Production Ready)         │
│      Defensive ETL + REST API + PostgreSQL          │
└─────────────────────────────────────────────────────┘

[ COMETA API ]
      ↓
[ API Container (FastAPI :8000) ] ← src/api_cometa.py (sanitization)
      ↓
[ ETL Container (APScheduler) ]   ← src/etl_worker.py + etl_service.py
    ├─ Defensive validation (src/App/shared/utils.py)
    ├─ Type checking + unwrap logic
    └─ Structured logging with data shape
      ↓
[ PostgreSQL Container ]
    ├─ vendas (7,197 rows)
    └─ estoque (2,070 rows)
```

## ✨ Destaques

✅ **Resiliente**: Continua processando com dados inconsistentes  
✅ **Observável**: Logging estruturado com contexto detalhado  
✅ **Escalável**: ThreadPoolExecutor com 8 workers paralelos  
✅ **Configurável**: Intervalo ETL ajustável via `.env`  
✅ **Graceful**: SIGTERM handling com cleanup  
✅ **Multi-Container**: Separação de concerns (API / ETL / DB)

## Fluxo de Dados

1. **Extração** (Container ETL): `CometaClient` busca dados da API Cometa a cada 5 minutos
2. **Transformação** (Container ETL): `flatten_vendas()` e `flatten_estoque()` desplanificam dados
3. **Carga** (Container ETL): `DatabaseClient` insere dados em PostgreSQL
4. **Exposição** (Container API): FastAPI lê do banco e retorna JSON protegido com HTTPBearer

**Benefícios da Separação**:
- ✅ ETL falha → API continua servindo dados
- ✅ API falha → ETL continua coletando dados
- ✅ Observabilidade isolada (logs, métricas, restart individual)
- ✅ Escalabilidade (ETL pode ter múltiplas réplicas)

## Estrutura de Dados

### Vendas (Tabela: `vendas`)
- **Antes**: Array aninhado com LOJA (dict) e VENDAS (list)
- **Depois**: Cada venda = linha com colunas:
  - `data`: Date
  - `loja_id`: Integer
  - `nome_loja`: String
  - `cnpj_loja`: String
  - `ean`: String
  - `cod_interno`: String
  - `plu`: Integer
  - `produto`: String
  - `qtd`: Float
  - `venda`: Float
  - `custo`: Float

### Estoque (Tabela: `estoque`)
- **Antes**: Array com dados variados
- **Depois**: Snapshot normalizado com colunas:
  - `snapshot_ts`: DateTime
  - `loja_id`: Integer
  - `codigo_produto`: String
  - `descricao_produto`: String
  - `ean`: String
  - `estq_loja`: Integer
  - `estq_avaria`: Integer

## Setup

### 1. Variáveis de Ambiente
```bash
cp .env.example .env
# Editar .env com credenciais reais
```

### 2. Docker Compose
```bash
docker compose -f docker/docker-compose.yml up --build
```

**Serviços iniciados**:
- `bi_cometa_db` - PostgreSQL 15
- `bi_cometa_api` - FastAPI na porta 8000
- `bi_cometa_etl` - ETL Worker (executa a cada 5 min)

**Verificar logs**:
```bash
docker logs -f bi_cometa_etl   # ETL jobs execution
docker logs -f bi_cometa_api   # HTTP requests
```

### 3. Manual (Desenvolvimento)
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure .env
export $(cat .env | xargs)

# Inicie PostgreSQL separadamente
python -m uvicorn main:app --reload
```

## APIs

### 🔐 Autenticação
Todas as rotas `/api/v1/*` são protegidas com **HTTPBearer authentication**.

**Header obrigatório**:
```
Authorization: Bearer <seu-token-aqui>
```

**Configuração**: Defina `API_AUTH_TOKEN` no `.env`:
```bash
API_AUTH_TOKEN=meu-token-secreto-forte-12345
```

📖 **Documentação completa**: Ver [PRODUCTION_SECURITY.md](docs/PRODUCTION_SECURITY.md)

---

### GET `/health`
**Público** (sem autenticação).

Health check simples.

### GET `/api/v1/vendas`
**Protegido** (requer Bearer token).

Retorna todas as vendas (sem paginação).
```json
[
  {
    "id": 1,
    "data": "2025-12-01",
    "loja_id": 3,
    "nome_loja": "03- OL PAIVA",
    "cnpj_loja": "06887668000340",
    "produto": "Iog Vale Milk...",
    "qtd": 6,
    "venda": 22.74,
    "custo": 2.65,
    "created_at": "2025-02-10T10:30:00"
  },
  ...
]
```

### GET `/api/v1/estoque`
**Protegido** (requer Bearer token).

Retorna snapshot atual de estoque (sem paginação).
```json
[
  {
    "id": 1,
    "snapshot_ts": "2025-02-10T10:30:00",
    "loja_id": 1,
    "codigo_produto": "142289",
    "descricao_produto": "Iog Vale Milk Bicamada 130G Morango",
    "ean": "7898200380953",
    "estq_loja": 27,
    "estq_avaria": 4
  },
  ...
]
```

## ETL

Executa a cada 1 hora (configurável via `ETL_INTERVAL_HOURS`):
1. **Estoque**: Deleta snapshot anterior, insere novo (snapshot atual)
2. **Vendas**: Deleta dados do mês inteiro, insere novo batch (mês atual)

## Logging

Todos os processos loggam em:
- **Nível**: INFO (configurável via `LOG_LEVEL`)
- **Formato**: `timestamp | level | module | message`

Exemplo:
```
2025-02-10 10:30:00,123 | INFO     | CometaClient          | Estoque request successful
2025-02-10 10:30:05,456 | INFO     | DatabaseClient        | Upserted vendas. Deleted=1500 Inserted=1600
```

## Profissionalismo

- ✅ **Modularidade**: Separação clara de responsabilidades
- ✅ **Configuração**: Pydantic Settings com validação automática
- ✅ **Segurança**: HTTPBearer authentication + CORS + GZip
- ✅ **Type hints**: Tipagem em todo o código
- ✅ **Logging**: Rastreamento de todos os processos
- ✅ **Validação**: Conversões seguras de tipos
- ✅ **Documentação**: Docstrings em todos os métodos
- ✅ **Transacionalidade**: ACID no banco de dados
- ✅ **Resiliência**: Tratamento de erros e timeouts
- ✅ **Docker**: Non-root user + network isolation

## Performance

- **Vendas**: Paralelo (8 workers) por loja
- **API**: Sem paginação, direto do banco ordenado por índices
- **Estoque**: Snapshot (replace all, não incremental)
- **Banco**: SQLAlchemy com `pool_pre_ping` para reconexão automática

## Roadmap

### Implementado ✅
- [x] HTTPBearer authentication
- [x] Pydantic Settings validation
- [x] CORS + GZip middlewares
- [x] Docker security hardening
- [x] PostgreSQL network isolation

### Planejado
- [ ] Rate limiting (throttling)
- [ ] JWT tokens com expiração
- [ ] Health check de dependências (DB, API)
- [ ] Métricas Prometheus
- [ ] Alertas de falhas de ETL
- [ ] Retry automático com exponential backoff
- [ ] Partição de tabelas por data

---

## � Quick Start (3 passos)

```bash
# 1. Configure variáveis
cp .env.example .env
nano .env  # Edite com credenciais reais

# 2. Inicie sistema
docker compose up --build -d

# 3. Valide saúde
curl http://localhost:8000/health
docker logs bi_cometa_etl --tail 50
```

---

## 🛡️ Validação em 5 Camadas

O sistema detecta e trata dados inconsistentes **sem interromper** o processamento:

```python
# Camada 1: Response Validation (api_cometa.py)
if response is None → return []

# Camada 2: Input Type (utils.py)
if not isinstance(vendas_list, list) → return []

# Camada 3: Item Structure (utils.py)
if isinstance(item, list) → unwrap_list()
if not isinstance(item, dict) → log WARNING, continue

# Camada 4: Per-Record (utils.py)
for venda in vendas:
    if not isinstance(venda, dict) → skip

# Camada 5: Database (SQLAlchemy)
if constraint fails → log ERROR, rollback, re-raise
```

### Exemplo Real

```
Problema: Loja 41 retorna [[],[],[],[]] (lista de listas vazias)

❌ Sem Defensive:
   AttributeError: 'list' object has no attribute 'get'  
   → Job interrompe, 0 vendas processadas

✅ Com Defensive:
   WARNING | flatten_vendas: item[0] é lista vazia ou sem dict
                             shape=list(len=0, first_item_type=empty)
   → Item ignorado, lojas restantes continuam
   → 7,197 vendas processadas com sucesso
   → Log estruturado com contexto para debugging
```

---

## 📊 Performance

| Métrica | Valor |
|---------|-------|
| **Duration** | 10.75 segundos |
| **Lojas** | 45/45 sucesso |
| **Vendas** | 7,197 armazenadas |
| **Throughput** | 862 records/seg |
| **Memory** | 680MB / 1GB limit |
| **Frequency** | 5 minutos (configurável) |

---

## 🔧 Configuração

**Arquivo**: `.env`

```env
# Database
DATABASE_URL=postgresql://bi_user:password@db:5432/bi_cometa

# API Cometa
COMETA_BASE_URL=https://api.cometa.com.br
COMETA_TOKEN=sk_live_xxxxx

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# ⭐ ETL Interval (em MINUTOS - DEFAULT: 5)
ETL_INTERVAL_MINUTES=5

# Logging
LOG_LEVEL=INFO
```

---

## 📁 Estrutura

```
BI_COMETA/
├── docker/
│   ├── Dockerfile           # API container
│   ├── Dockerfile.etl       # ETL container  
│   └── docker-compose.yml   # 3 services (db, app, etl)
│
├── src/
│   ├── main.py              # FastAPI entry point
│   ├── etl_worker.py        # ETL entry point (BlockingScheduler)
│   ├── api_cometa.py        # API client + sanitization layer
│   ├── config.py            # Configuração (Pydantic Settings)
│   │
│   └── App/
│       ├── api/
│       ├── core/
│       │   └── schemas.py  # Pydantic models (optional)
│       ├── etl/
│       │   ├── etl_service.py      # Orchestration
│       │   └── database_client.py  # DB operations
│       └── shared/
│           └── utils.py           # ⭐ Defensive logic (flatten_*)
│
├── tests/
├── .env.example
├── requirements.txt
└── docs/
    ├── QUICK_REFERENCE.md     # ⭐ Comece aqui
    ├── DEFENSIVE_REFACTOR.md  # Deep dive validação
    ├── MONITORING_GUIDE.md    # Monitoramento avançado
    └── ARCHITECTURE.md        # Arquitetura completa
```

---

## 🚨 Monitoramento Rápido

```bash
# Health checks
curl http://localhost:8000/health        # API
curl http://localhost:8000/health/db     # Database

# Últimos logs ETL
docker logs bi_cometa_etl --tail 50

# Taxa de sucesso
docker logs bi_cometa_etl | grep "collection summary"

# Detectar inconsistências
docker logs bi_cometa_etl | grep "flatten_vendas: item"

# Próxima execução
docker logs bi_cometa_etl | grep "next run"
```

---

## 🆘 Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Container não inicia | `docker compose logs db` - Ver erro específico |
| Database connection refused | `docker compose up -d db` - Aguardar healthcheck |
| ETL não executa | `docker restart bi_cometa_etl` - Reiniciar |
| Múltiplas lojas com 0 vendas | Check se padrão repetido - contatar Cometa |

Mais detalhes: Ver [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)

---

## 📚 Documentação Completa

| Documento | Propósito |
|-----------|----------|
| **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** | ⭐ Comece aqui - Comandos rápidos e troubleshooting |
| **[DEFENSIVE_REFACTOR.md](docs/DEFENSIVE_REFACTOR.md)** | Deep dive na lógica defensiva com exemplos |
| **[MONITORING_GUIDE.md](docs/MONITORING_GUIDE.md)** | Monitoramento avançado e diagnóstico |
| **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Arquitetura técnica completa, fluxos, modelos |
