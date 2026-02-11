# BI_COMETA - Arquitetura de Microserviços

## 🏗️ Nova Arquitetura (v2.0)

### Separação de Responsabilidades

O sistema foi refatorado de aplicação monolítica para **arquitetura de microserviços** com 3 containers:

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network (bi_network)             │
│                                                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐ │
│  │              │      │              │      │          │ │
│  │  PostgreSQL  │◄─────┤  ETL Worker  │      │  FastAPI │ │
│  │              │      │              │      │   API    │ │
│  │   (db:5432)  │◄─────┼──────────────┘      │          │ │
│  │              │      │                     │ (app:8000)│ │
│  └──────────────┘      └─────────────────────┴──────────┘ │
│        ▲                                           │       │
│        │ Isolado                                   │       │
│        │ (sem porta exposta)             Porta 8000 exposta│
└────────┼───────────────────────────────────────────┼───────┘
         │                                           │
         │                                           ▼
         │                                    Consumidores
         │                                  (Power BI, cURL)
         │
    (acesso direto bloqueado)
```

---

## 📦 Containers

### 1. PostgreSQL Database (`db`)
- **Image**: `postgres:15`
- **Função**: Armazenamento persistente de dados
- **Network**: `bi_network` (isolado)
- **Porta**: 5432 (não exposta externamente)
- **Healthcheck**: `pg_isready` a cada 10s
- **Volumes**: `postgres_data:/var/lib/postgresql/data`

**Observabilidade**:
```bash
# Status
docker logs bi_cometa_db --tail 50

# Conectar diretamente
docker exec -it bi_cometa_db psql -U bi_user -d bi_cometa
```

---

### 2. ETL Worker (`etl`)
- **Image**: Custom (Dockerfile.etl)
- **Função**: Extração, transformação e carga de dados
- **Entry Point**: `etl_worker.py`
- **Scheduler**: APScheduler (BlockingScheduler)
- **Intervalo**: Configurável via `ETL_INTERVAL_MINUTES` (padrão: 5 min)
- **Network**: `bi_network` (acesso ao DB)
- **Recursos**: CPU 1.0 / Memory 1G (com reservations)
- **User**: Non-root (`etluser` UID 1001)
- **Restart Policy**: `unless-stopped`

**Fluxo de Execução**:
1. Inicializa `CometaClient` → API externa
2. Inicializa `DatabaseClient` → PostgreSQL
3. Cria `ETLService(cometa_client, db_client)`
4. Agenda job recorrente a cada `ETL_INTERVAL_MINUTES`
5. Executa:
   - `processar_vendas()` → ThreadPool 8 workers
   - `processar_estoque()` → Snapshot replacement
6. Logs detalhados com timestamps e duração

**Shutdown Graceful**:
- Captura `SIGTERM` / `SIGINT`
- Finaliza job em execução
- Desliga scheduler com `wait=True`

**Observabilidade**:
```bash
# Logs em tempo real
docker logs -f bi_cometa_etl

# Filtrar apenas jobs completos
docker logs bi_cometa_etl | grep "ETL Job Completed"

# Verificar erros
docker logs bi_cometa_etl | grep -E "ERROR|EXCEPTION"

# Estatísticas de recursos
docker stats bi_cometa_etl
```

---

### 3. FastAPI API (`app`)
- **Image**: Custom (Dockerfile)
- **Função**: API REST para consumo de dados
- **Entry Point**: `main.py` (uvicorn)
- **Network**: `bi_network` (acesso ao DB)
- **Porta**: 8000 (exposta publicamente)
- **User**: Non-root (`appuser` UID 1000)
- **Restart Policy**: `unless-stopped`

**Endpoints**:
- `GET /health` - Health check da API (público)
- `GET /health/db` - Health check do PostgreSQL (público)
- `GET /api/v1/vendas` - Todas as vendas (protegido)
- `GET /api/v1/estoque` - Snapshot de estoque (protegido)
- `GET /docs` - Swagger UI (público)
- `GET /openapi.json` - OpenAPI schema (público)

**Responsabilidades**:
- ✅ Servir dados via HTTP
- ✅ Autenticação HTTPBearer
- ✅ CORS + GZip middlewares
- ❌ **NÃO** executa ETL (delegado ao container `etl`)

**Observabilidade**:
```bash
# Logs HTTP requests
docker logs -f bi_cometa_api

# Health checks
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

---

## ⚙️ Configuração

### Variáveis de Ambiente

#### ETL Interval (MUDANÇA CRÍTICA)
```bash
# .env
ETL_INTERVAL_MINUTES=5   # Executa a cada 5 minutos
```

**Antes**: `ETL_INTERVAL_HOURS=1` (1 hora)  
**Depois**: `ETL_INTERVAL_MINUTES=5` (5 minutos)

**Range válido**: 1-1440 minutos (1 min até 24 horas)

**Exemplos**:
- `ETL_INTERVAL_MINUTES=1` → Executa a cada 1 minuto (desenvolvimento)
- `ETL_INTERVAL_MINUTES=5` → Default (produção)
- `ETL_INTERVAL_MINUTES=15` → A cada 15 minutos
- `ETL_INTERVAL_MINUTES=60` → A cada 1 hora

---

## 🚀 Deploy

### Local Development
```bash
# 1. Configurar .env
cp .env.example .env
# Editar: ETL_INTERVAL_MINUTES=5, API_AUTH_TOKEN, etc.

# 2. Build e Start
cd docker
docker-compose up --build

# 3. Verificar serviços
docker ps
# Deve mostrar: bi_cometa_db, bi_cometa_api, bi_cometa_etl
```

### Verificação de Logs
```bash
# PostgreSQL
docker logs bi_cometa_db --tail 20

# ETL Worker
docker logs bi_cometa_etl --tail 50

# FastAPI
docker logs bi_cometa_api --tail 30
```

### Restart Individual
```bash
# Apenas ETL (sem afetar API)
docker restart bi_cometa_etl

# Apenas API (sem afetar ETL)
docker restart bi_cometa_api

# Apenas DB (reinicia dependentes)
docker restart bi_cometa_db
```

---

## 🔍 Observabilidade

### Monitoramento de ETL

#### Logs de Job Execution
```bash
docker logs bi_cometa_etl 2>&1 | grep "ETL Job"
```

**Output esperado**:
```
2026-02-10 10:00:00 | INFO | ETL_Worker | ETL Job Started at 2026-02-10T10:00:00
2026-02-10 10:02:35 | INFO | ETL_Worker | ETL Job Completed at 2026-02-10T10:02:35 (duration: 155.23 seconds)
2026-02-10 10:05:00 | INFO | ETL_Worker | ETL Job Started at 2026-02-10T10:05:00
```

#### Próximo Job Agendado
```bash
docker logs bi_cometa_etl | grep "Next ETL run scheduled"
```

#### Estatísticas de Vendas Processadas
```bash
docker logs bi_cometa_etl | grep "Loja.*vendas processadas"
```

**Output esperado**:
```
2026-02-10 10:01:23 | INFO | ETLService | Loja 3: 1234 vendas processadas
2026-02-10 10:01:45 | INFO | ETLService | Loja 5: 987 vendas processadas
```

### Health Checks

#### API Health
```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "api",
  "version": "1.1.0"
}
```

#### Database Health
```bash
curl http://localhost:8000/health/db
```

**Response (healthy)**:
```json
{
  "status": "healthy",
  "service": "database",
  "type": "postgresql"
}
```

**Response (unhealthy)**:
```json
{
  "status": "unhealthy",
  "service": "database",
  "error": "connection refused"
}
```

---

## 🛡️ Tolerância a Falhas

### Cenário 1: ETL Falha
```
ETL Worker crash/erro
       ↓
API continua servindo dados
       ↓
PostgreSQL mantém último snapshot válido
       ↓
ETL reinicia (restart: unless-stopped)
       ↓
Próximo job sincroniza dados
```

**Impacto**: ✅ Zero downtime na API

### Cenário 2: API Falha
```
FastAPI crash
       ↓
ETL continua processando dados
       ↓
PostgreSQL continua recebendo updates
       ↓
API reinicia e serve dados atualizados
```

**Impacto**: ✅ Dados continuam sendo coletados

### Cenário 3: PostgreSQL Falha
```
Database crash
       ↓
API retorna 503 em /health/db
       ↓
ETL aguarda reconnect
       ↓
PostgreSQL reinicia (Docker healthcheck)
       ↓
Serviços reconectam automaticamente
```

**Impacto**: ⚠️ Downtime temporário até DB recovery

---

## 📊 Recursos e Limites

### ETL Worker Resources
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'      # Máximo 1 CPU core
      memory: 1G       # Máximo 1GB RAM
    reservations:
      cpus: '0.5'      # Garante 0.5 CPU
      memory: 512M     # Garante 512MB RAM
```

**Justificativa**:
- ThreadPoolExecutor (8 workers) → CPU-bound
- Processamento de JSON grandes → Memory-bound
- Limites previnem OOM (Out of Memory)

**Monitorar**:
```bash
docker stats bi_cometa_etl
```

**Output**:
```
NAME            CPU %    MEM USAGE / LIMIT    MEM %
bi_cometa_etl   45.2%    680MiB / 1GiB        66.4%
```

---

## 🔄 Ciclo de Vida de um Job ETL

### 1. Trigger (APScheduler)
```
Scheduler tick (00:00, 00:05, 00:10...)
       ↓
run_etl_job() invoked
```

### 2. Initialization
```python
CometaClient(base_url, email, password)  # API externa
DatabaseClient(db_url)                   # PostgreSQL
ETLService(cometa, db)                   # Orchestrator
```

### 3. Vendas Processing
```
list_lojas() → [3, 5, 8, 10, ...]
       ↓
ThreadPoolExecutor (8 workers)
       ↓
Parallel: get_vendas_loja(loja_id, inicio, fim)
       ↓
flatten_vendas() → desplanifica nested arrays
       ↓
upsert_vendas(flat_data) → INSERT ON CONFLICT UPDATE
```

### 4. Estoque Processing
```
get_estoque() → API call
       ↓
flatten_estoque() → normaliza keys
       ↓
replace_estoque(flat_data) → DELETE ALL + INSERT (snapshot)
```

### 5. Completion
```
Log: "ETL Job Completed (duration: 155.23s)"
       ↓
Aguarda próximo trigger (5 min depois)
```

---

## 🐛 Troubleshooting

### ETL não executa a cada 5 minutos
**Verificar**:
```bash
# 1. Conferir variável de ambiente
docker exec bi_cometa_etl printenv ETL_INTERVAL_MINUTES

# 2. Verificar logs de scheduler
docker logs bi_cometa_etl | grep "interval="
```

**Solução**: Atualizar `.env` e `docker-compose restart etl`

---

### API não conecta com PostgreSQL
**Verificar**:
```bash
# 1. Database está healthy?
docker ps --filter "name=bi_cometa_db" --format "{{.Status}}"

# 2. Testar conectividade
docker exec bi_cometa_api ping -c 2 db

# 3. Health check endpoint
curl http://localhost:8000/health/db
```

**Solução**: Aguardar healthcheck do DB (pode levar até 30s no startup)

---

### ETL consome muita memória
**Verificar**:
```bash
docker stats bi_cometa_etl --no-stream
```

**Se > 900MB**:
- Reduzir `ThreadPoolExecutor` workers (8 → 4)
- Aumentar limite em docker-compose: `memory: 2G`
- Processar lojas em batches menores

---

## 📈 Métricas Recomendadas

### ETL Performance
- **Job Duration**: Tempo total de execução (target: <3 min)
- **Vendas Fetched**: Total de vendas processadas por job
- **Error Rate**: % de lojas com falha de fetch
- **Memory Peak**: Uso máximo de RAM durante job

### API Performance
- **Request Latency**: Tempo de response (target: <2s)
- **Database Query Time**: Tempo de `fetch_vendas()` (target: <1s)
- **Error Rate**: % de requests 5xx

### Database
- **Table Size**: `pg_total_relation_size('vendas')`
- **Query Performance**: `EXPLAIN ANALYZE SELECT * FROM vendas`
- **Connection Pool**: Número de conexões ativas

---

## 🔮 Roadmap

### Implementado ✅
- [x] Separação ETL → container dedicado
- [x] Intervalo configurável em minutos
- [x] Health checks de API e DB
- [x] Resource limits no ETL
- [x] Shutdown graceful com SIGTERM
- [x] Logs estruturados com timestamps

### Planejado
- [ ] Prometheus metrics exporters
- [ ] Grafana dashboards (ETL duration, API latency)
- [ ] Alertmanager (ETL failures, DB down)
- [ ] Retry logic com exponential backoff
- [ ] Dead Letter Queue para vendas com erro
- [ ] Particionamento de tabelas por data

---

## 📚 Arquivos Criados/Modificados

### Novos Arquivos
1. `docker/Dockerfile.etl` - Dockerfile para container ETL
2. `src/etl_worker.py` - Entry point do ETL Worker
3. `docs/MICROSERVICES_ARCHITECTURE.md` - Este documento

### Modificados
1. `docker/docker-compose.yml` - Adicionado serviço `etl`
2. `src/main.py` - Removido APScheduler (delegado ao ETL)
3. `src/App/core/config.py` - `ETL_INTERVAL_HOURS` → `ETL_INTERVAL_MINUTES`
4. `.env.example` - Atualizado com `ETL_INTERVAL_MINUTES=5`

---

**Versão**: 2.0  
**Arquitetura**: Microserviços (3 containers)  
**Frequência ETL**: 5 minutos (configurável)  
**Tolerância a Falhas**: Alta (isolamento de serviços)

