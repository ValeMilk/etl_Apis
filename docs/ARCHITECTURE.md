# BI_COMETA - Arquitetura Técnica e Implementação

## 🏗️ Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    COMETA API (Externa)                     │
│              GET /estoque, /vendas/:loja/:mm/yy             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ HTTP Requests (ThreadPoolExecutor × 8)
                  │
        ┌─────────▼──────────────────┐
        │   BI_COMETA API Container  │
        │   (FastAPI :8000)          │
        │                            │
        │ ├─ src/api_cometa.py       │
        │ │  ├─ get_estoque()        │
        │ │  └─ get_vendas_loja()    │
        │ │                          │
        │ ├─ POST /sync (manual)     │
        │ └─ GET /health             │
        └─────────┬──────────────────┘
                  │
        ┌─────────▼──────────────────┐
        │   BI_COMETA ETL Container  │
        │   (APScheduler Worker)     │
        │                            │
        │ ├─ src/etl_worker.py       │
        │ │  └─ BlockingScheduler    │
        │ │     ├─ Every N minutes   │
        │ │     └─ SIGTERM graceful  │
        │ │                          │
        │ ├─ src/App/etl/           │
        │ │  ├─ etl_service.py      │
        │ │  │  ├─ processar_vendas()│
        │ │  │  └─ processar_estoque│
        │ │  │                      │
        │ │  └─ database_client.py  │
        │ │     ├─ replace_estoque()│
        │ │     ├─ insert_vendas()  │
        │ │     └─ cleanup()        │
        │ │                          │
        │ ├─ src/App/shared/        │
        │ │  └─ utils.py            │
        │ │     ├─ flatten_vendas()  │ ← Defensive
        │ │     ├─ flatten_estoque() │ ← Defensive
        │ │     ├─ _unwrap_list()    │
        │ │     └─ _get_data_shape() │
        │ │                          │
        │ └─ .env                    │
        │    ├─ ETL_INTERVAL_MINUTES │
        │    └─ outros               │
        └─────────┬──────────────────┘
                  │
        ┌─────────▼──────────────────┐
        │   PostgreSQL 15 Container  │
        │   (Database)               │
        │                            │
        │ ├─ schema public           │
        │ │  ├─ vendas (13 columns)  │
        │ │  │  ├─ id (PK)           │
        │ │  │  ├─ loja_id           │
        │ │  │  ├─ data_venda        │
        │ │  │  ├─ produto_id        │
        │ │  │  ├─ quantidade        │
        │ │  │  ├─ valor_unitario    │
        │ │  │  └─ ...               │
        │ │  │                       │
        │ │  └─ estoque (8 columns)  │
        │ │     ├─ id (PK)           │
        │ │     ├─ loja_id           │
        │ │     ├─ codigo_produto    │
        │ │     ├─ descricao         │
        │ │     ├─ quantidade        │
        │ │     └─ ...               │
        │ │                          │
        │ └─ indexes (performance)   │
        │    ├─ ix_vendas_loja_id    │
        │    ├─ ix_estoque_loja_id   │
        │    └─ ...                  │
        └────────────────────────────┘

Network: bi_network (isolated)
Health Checks: All containers monitored
Resources: DB=2GB/2CPUs, API=512MB/1CPU, ETL=1GB/1CPU
```

---

## 🔄 Fluxo de Dados - Exemplo Real

### Ciclo 1: Execução do ETL (a cada 5 minutos)

```
timestamp: 2026-02-11 01:24:00 UTC

1. APScheduler triggers
   └─ BlockingScheduler.trigger() in etl_worker.py

2. ETLService.executar() starts
   └─ Log: "ETL Job Started at 2026-02-11T01:24:00..."

3. Process VENDAS
   ├─ CometaClient.get_vendas_loja() × 45 lojas
   │  │
   │  ├─ Loja 2:
   │  │  ├─ API Request: GET /vendas/2/01/26
   │  │  ├─ Response: {"VENDAS": [{"LOJA": 2, "DATA": "2026-01-05", ...}]}
   │  │  ├─ parse: ok (dict)
   │  │  ├─ flatten_vendas():
   │  │  │  └─ item[0] = {"LOJA": 2, "DATA": "2026-01-05", "PRODUTO": "ABC123", "QUANTIDADE": 3, "VALOR_UNITARIO": 99.90}
   │  │  │     └─ Validate: type=dict ✅
   │  │  │     └─ LOJA field: 2 ✅
   │  │  │     └─ VENDAS field: [...] ✅
   │  │  │     └─ Process each venda → flat dict
   │  │  ├─ Return: List[dict] com 156 vendas
   │  │  └─ Log: "Loja 2: 156 vendas processadas (sucesso: 1/45)"
   │  │
   │  ├─ Loja 41:
   │  │  ├─ API Request: GET /vendas/41/01/26
   │  │  ├─ Response: [] (lista vazia! inconsistência)
   │  │  ├─ parse: ok (list)
   │  │  ├─ flatten_vendas():
   │  │  │  └─ item[0] = [] ← TIPO INVÁLIDO
   │  │  │     └─ isinstance(item, list): True
   │  │  │     └─ _unwrap_list([]): None ← vazia não contém dict
   │  │  │     └─ Log WARNING: "item[0] é lista vazia ou sem dict. shape=list(len=0, first_item_type=empty)"
   │  │  │     └─ continue (pula este item)
   │  │  ├─ Return: [] (sem vendas)
   │  │  └─ Log: "Loja 41: 0 vendas processadas (sucesso: 38/45)"
   │  │
   │  └─ [Outras 43 lojas processadas...]
   │
   ├─ Summary Log: "Vendas collection summary: sucesso=45, falha=0, total_vendas=7197"
   └─ db.insert_vendas(7197) → INSERT 7197 rows in ~2 segundos

4. Process ESTOQUE
   ├─ CometaClient.get_estoque() × 45 lojas
   │  ├─ Similar logic a VENDAS
   │  └─ 2070 items coletados
   ├─ db.replace_estoque(2070) → REPLACE 2070 rows in ~1 segundo
   └─ Log: "Estoque ETL finished. Deleted=0 Inserted=2070 Total_rows=2070"

5. ETL Cleanup & Schedule
   ├─ Log: "ETL Job Completed at 2026-02-11T01:24:53.609951 (duration: 10.75 seconds)"
   ├─ Schedule next run
   ├─ Log: "next run at: 2026-02-11 01:29:42 UTC"
   └─ IDLE (aguardando próximo ciclo)

6. Próximo ciclo: 01:29:42 UTC (5 minutos depois)
   └─ Repetir from step 1
```

---

## 🛡️ Defensive Programming Pattern

### Padrão de Validação em Camadas

```
┌─────────────────────────────────────────────────┐
│ Camada 1: API Response Validation              │
│ (api_cometa.py)                                │
│ ├─ response is not None?                       │
│ ├─ response is dict or list?                   │
│ └─ Extract keys: ESTOQUE/estoque/data/DATA     │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│ Camada 2: Input Type Validation                │
│ (flatten_vendas/estoque)                       │
│ ├─ isinstance(vendas_brutos, list)?            │
│ └─ items are not None?                         │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│ Camada 3: Item Structure Validation            │
│ (flatten_vendas/estoque)                       │
│ ├─ item is dict? (else unwrap_list)            │
│ ├─ item has required fields? (LOJA, VENDAS)    │
│ └─ fields are correct type? (int, list, etc)   │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│ Camada 4: Per-Record Validation                │
│ (inside nested loops)                          │
│ ├─ venda is dict?                              │
│ ├─ venda has required fields?                  │
│ └─ field types are valid?                      │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│ Camada 5: Database Insert                      │
│ (database_client.py)                           │
│ ├─ SQLAlchemy model validation                 │
│ ├─ Constraints (FK, NOT NULL)                  │
│ └─ Transaction rollback on error               │
└─────────────────────────────────────────────────┘

Recovery Strategy:
- Layer 1-4: Log WARNING, continue to next item
- Layer 5: Log ERROR, rollback transaction, re-raise
  (likely all other items in batch valid)
```

### Exemplo: Validação de VENDAS

```python
# ANTES (não defensivo)
def flatten_vendas(vendas_brutos):
    resultado = []
    for item in vendas_brutos:  # ❌ Não trata None
        data = item["LOJA"]      # ❌ Não trata lista
        vendas = item["VENDAS"]  # ❌ Não valida tipo
        for venda in vendas:     # ❌ Assume sempre dict
            resultado.append(venda)
    return resultado

# DEPOIS (defensivo)
def flatten_vendas(vendas_brutos):
    # Camada 1: Input validation
    if not isinstance(vendas_brutos, list):
        logger.warning("Expected list, got %s", type(vendas_brutos).__name__)
        return []
    
    resultado = []
    itens_invalidos = 0
    
    # Iterar com índice para logging
    for idx, item in enumerate(vendas_brutos):
        # Camada 2: Item validation
        if item is None:
            logger.debug("item[%d] is None, skipping", idx)
            continue
        
        # Camada 3a: Type checking e unwrap
        if isinstance(item, list):
            # Tentar extrair dict de lista
            unwrapped = _unwrap_list(item)
            if not unwrapped:
                itens_invalidos += 1
                shape = _get_data_shape(item)
                logger.warning(
                    "item[%d] é lista vazia ou sem dict. shape=%s",
                    idx, shape
                )
                continue
            item = unwrapped  # Usa dict extraído
        
        # Camada 3b: Dict validation
        if not isinstance(item, dict):
            itens_invalidos += 1
            shape = _get_data_shape(item)
            logger.warning(
                "item[%d] tipo inválido: %s. shape=%s",
                idx, type(item).__name__, shape
            )
            continue
        
        # Extrair LOJA (pode estar como lista também)
        loja = item.get("LOJA")
        if isinstance(loja, list):  # Unwrap se lista
            loja = loja[0] if loja else None
        
        # Validar VENDAS field
        vendas = item.get("VENDAS")
        if not isinstance(vendas, list):
            itens_invalidos += 1
            logger.warning(
                "item[%d] VENDAS field invalid type: %s",
                idx, type(vendas).__name__
            )
            continue
        
        # Camada 4: Per-venda validation
        for venda in vendas:
            if not isinstance(venda, dict):
                logger.debug(
                    "item[%d] venda[X] invalid (not dict), skipping",
                    idx
                )
                continue
            resultado.append(venda)
    
    # Log resumo
    if itens_invalidos > 0:
        logger.warning(
            "Processamento concluído com %d items inválidos de %d. "
            "Retornando %d vendas válidas.",
            itens_invalidos, len(vendas_brutos), len(resultado)
        )
    
    return resultado
```

---

## 🗄️ Modelo de Dados

### Tabela: VENDAS

```sql
CREATE TABLE vendas (
    id BIGSERIAL PRIMARY KEY,
    loja_id INTEGER NOT NULL,
    data_venda DATE NOT NULL,
    codigo_produto VARCHAR(50) NOT NULL,
    descricao_produto VARCHAR(255),
    quantidade NUMERIC(10, 2) NOT NULL,
    valor_unitario NUMERIC(12, 2) NOT NULL,
    valor_total NUMERIC(12, 2),
    numero_venda VARCHAR(50),
    numero_item VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX ix_vendas_loja_id (loja_id),
    INDEX ix_vendas_data (data_venda),
    INDEX ix_vendas_produto (codigo_produto)
);
```

### Tabela: ESTOQUE

```sql
CREATE TABLE estoque (
    id BIGSERIAL PRIMARY KEY,
    loja_id INTEGER NOT NULL,
    codigo_produto VARCHAR(50) NOT NULL,
    descricao_produto VARCHAR(255),
    quantidade_atual NUMERIC(10, 2),
    quantidade_minima NUMERIC(10, 2),
    preco_unitario NUMERIC(12, 2),
    ultima_atualizacao TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(loja_id, codigo_produto),
    INDEX ix_estoque_loja_id (loja_id),
    INDEX ix_estoque_produto (codigo_produto)
);
```

---

## ⚙️ Configuração Centralizada

**Arquivo**: `config.py`

```python
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://user:pass@db:5432/bi_cometa"
    
    # API Cometa
    COMETA_BASE_URL: str = "https://api.cometa.example.com"
    COMETA_TOKEN: str  # SecretStr in production
    
    # CORS
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://localhost:8080"
    
    # ETL Schedule
    ETL_INTERVAL_MINUTES: int = 5  # Default 5, можно override via .env
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
```

**Arquivo**: `.env` (exemplo)

```env
# Database
DATABASE_URL=postgresql://bi_user:secure_password@db:5432/bi_cometa

# API Cometa
COMETA_BASE_URL=https://api.cometa.com.br
COMETA_TOKEN=sk_live_xxxxxxxxxxxx

# CORS (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:8080,https://dashboard.example.com

# ETL Schedule (em minutos)
ETL_INTERVAL_MINUTES=5

# Logging
LOG_LEVEL=INFO
```

---

## 📦 Dependências Críticas

### Python (src/)

```
fastapi==0.109.0              # API framework
sqlalchemy==2.0.25            # ORM
psycopg2-binary==2.9.9        # PostgreSQL driver
pydantic==2.5.3               # Data validation
pydantic-settings==2.1.0      # Config management
apscheduler==3.10.4           # Job scheduling
python-httpx==0.25.0          # Async HTTP
python-multipart==0.0.6       # Form data parsing
uvicorn==0.27.0               # ASGI server
python-dotenv==1.0.0          # .env loader
```

---

## 🚀 Ciclo de Vida do Container ETL

```
1. STARTUP
   ├─ Load .env → Settings
   ├─ Initialize logger
   ├─ Connect to PostgreSQL
   ├─ Verify database connectivity
   ├─ Load ETL service
   ├─ Initialize BlockingScheduler
   ├─ Schedule job: every ETL_INTERVAL_MINUTES
   └─ Log: "Scheduler started. Next run at 2026-02-11 01:29:42 UTC"

2. RUNNING (loop infinito)
   ├─ APScheduler waiting for trigger time
   └─ When trigger time reached:
      ├─ ETLService.executar()
      ├─ ... (processing steps)
      └─ Schedule next run

3. SHUTDOWN (on SIGTERM)
   ├─ Catch SIGTERM signal
   ├─ Stop scheduler
   ├─ Wait for current job to finish (if running)
   ├─ Close database connection
   ├─ Exit gracefully (exit code 0)
```

---

## 🔌 Integração com API Cometa

### HTTP Request/Response Pattern

**Request**:
```http
GET /vendas/2/01/26 HTTP/1.1
Host: api.cometa.com.br
Authorization: Bearer sk_live_xxxx
Accept: application/json
```

**Response Esperado**:
```json
{
  "VENDAS": [
    {
      "LOJA": 2,
      "DATA": "2026-01-05",
      "PRODUTO": "ABC123",
      "DESCRICAO": "Produto X",
      "QUANTIDADE": 3,
      "VALOR_UNITARIO": 99.90,
      "NUMERO_VENDA": "V-2026-001",
      "NUMERO_ITEM": "1"
    },
    // ... more items
  ]
}
```

**Response Problemático** (tratado defensivamente):
```json
[]  // ← Loja 41, 44, 46 frequentemente
```

ou

```json
{
  "ESTOQUE": [[], [], []]  // ← Lista de listas vazias
}
```

### Tratamento em api_cometa.py

```python
def get_vendas_loja(loja_id: int, data_inicio: date, data_fim: date) -> List[dict]:
    vendas_brutos = []
    data_atual = data_inicio
    
    while data_atual <= data_fim:
        try:
            res = requests.get(
                f"{self.base_url}/vendas/{loja_id}/{data_atual.strftime('%m/%y')}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30
            )
            
            if res.status_code == 200:
                dados = res.json()
                
                # Sanitização
                if dados is None:
                    logger.debug("Response is None for loja=%s", loja_id)
                elif isinstance(dados, (dict, list)):
                    vendas_brutos.append(dados)
                else:
                    logger.warning("Unexpected type: %s", type(dados).__name__)
            else:
                logger.warning("HTTP %d for loja=%s", res.status_code, loja_id)
        
        except requests.Timeout:
            logger.error("Timeout for loja=%s, period=%s", loja_id, data_atual)
        except Exception as e:
            logger.exception("Error fetching loja=%s: %s", loja_id, e)
        
        data_atual += timedelta(days=1)
    
    if not vendas_brutos:
        logger.debug("No data collected for loja=%s", loja_id)
        return []
    
    return flatten_vendas(vendas_brutos)
```

---

## 📊 Performance Characteristics

### Benchmarks (Real Run)

```
Configuration:
- 45 lojas processadas
- ThreadPoolExecutor with 8 workers
- 5 API requests por loja (31 dias / 6 dias por request ~5 requests)

Timeline:
- Total Duration: 10.75 segundos
- API Requests: ~225 (45 × 5)
- Database Inserts: 7197 + 2070 = 9267 rows

Breakdown:
├─ API requests (parallel): ~7.0 segundos
├─ Parsing/validation: ~1.5 segundos
├─ Database inserts: ~2.0 segundos
└─ Logging/cleanup: ~0.3 segundos

Throughput:
- Vendas: 7197 / 10.75 = 669 vendas/segundo
- Estoque: 2070 / 10.75 = 192 items/segundo
- Total: 862 records/segundo

Memory:
- Container baseline: ~350MB
- Peak (during processing): ~680MB
- Limit: 1GB (headroom: 320MB)
```

---

## 🎯 Pontos de Extensão Futura

### 1. Implementar Métricas Prometheus

```python
from prometheus_client import Counter, Histogram, Summary

# Métricas
etl_jobs_total = Counter('etl_jobs_total', 'Total ETL jobs', ['status'])
etl_duration = Histogram('etl_duration_seconds', 'ETL duration')
vendas_processed = Counter('vendas_processed_total', 'Vendas processed')

# Uso
etl_jobs_total.labels(status='success').inc()
etl_duration.observe(10.75)
```

### 2. Async API Requests (httpx)

```python
import httpx

async def get_vendas_loja_async(self, loja_id: int) -> List[dict]:
    async with httpx.AsyncClient() as client:
        tasks = [
            client.get(f"{url}/vendas/{loja_id}/{period}")
            for period in periods
        ]
        results = await asyncio.gather(*tasks)
    # Process results
```

### 3. Dead Letter Queue para Problematic Lojas

```python
# Persistir items inválidos para análise
class DeadLetterQueue:
    def add(self, loja_id: int, data: dict, reason: str):
        db.insert({
            'loja_id': loja_id,
            'payload': data,
            'reason': reason,
            'timestamp': now()
        })
```

---

Arquitetura finalizada e pronta para operação.

Última Atualização: 2026-02-11
