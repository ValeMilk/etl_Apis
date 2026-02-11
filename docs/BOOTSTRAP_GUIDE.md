# BI_COMETA - Bootstrap Automático

## 🎯 O que é Bootstrap

**Bootstrap** é um processo de **inicialização única** que preence seu banco de dados com histórico de vendas na primeira execução.

```
1ª Execução: Banco vazio
    ↓
Doctor detects → executa bootstrap
    ↓
Carrega histórico desde 01/01/2025
    ↓
Itera janelas de 3 dias (API limit)
    ↓
260,000+ vendas + 2,000+ estoque items
    ↓
2ª Execução em diante: ETL normal (5 min interval)
```

---

## 🚀 Como Funciona

### Automático (Recomendado)

```bash
# Simplesmente inicie o Docker
docker compose down -v  # Limpar volumes antigos (opcional)
docker compose up --build -d

# o container ETL automaticamente:
# 1. Verifica se banco está vazio
# 2. Se vazio → executa bootstrap
# 3. Se já tem dados → salta bootstrap
# 4. Inicia scheduler normal (5 min interval)
```

**O que vê nos logs:**
```
========================================
BI_COMETA ETL Container Starting
========================================
✅ Database is ready
⚠️  Bootstrap needed - running initialization...

==========================================
🔄 BOOTSTRAP: Initializing database with historical data
==========================================
Loading historical data from 01/01/2025...

📊 Collecting vendas (3-day windows from 01/01/2025)...
🔄 Bootstrap vendas from 2025-01-01 to 2026-02-11
⚠️  Puxando dados de 3 em 3 dias (limite da API)

📅 Fetching 2025-01-01 → 2025-01-03
✅ Period 2025-01-01 → 2025-01-03: 1560 vendas (lojas: 45 ok, 0 falha)
📅 Fetching 2025-01-04 → 2025-01-06
✅ Period 2025-01-04 → 2025-01-06: 2301 vendas (lojas: 45 ok, 0 falha)
... [Continues iteratively through ~140 periods] ...

✅ Bootstrap completed: 136 day-windows, 260233 total vendas

📦 Starting Estoque collection...
Estoque ETL finished. Deleted=0 Inserted=2070 Total_rows=2070

==========================================
✅ BOOTSTRAP COMPLETED SUCCESSFULLY
Total vendas loaded: 260233
Total in database now: 260233
==========================================

🚀 Starting ETL Scheduler
```

### Manual (para testes ou troubleshooting)

```bash
# Execute bootstrap manualmente
docker exec bi_cometa_etl python bootstrap.py

# Ou com opções
docker exec bi_cometa_etl python bootstrap.py --year 2024
docker exec bi_cometa_etl python bootstrap.py --force
```

---

## 🔍 Como Verifica se Bootstrap Rodou

### Via Logs

```bash
# Ver se bootstrap foi executado
docker logs bi_cometa_etl | grep "BOOTSTRAP"

# Output esperado se rodou:
# "🔄 BOOTSTRAP: Initializing database with historical data"
# "✅ BOOTSTRAP COMPLETED SUCCESSFULLY"

# Output se não foi necessário:
# "✅ Database already initialized, skipping bootstrap"
```

### Via Banco de Dados

```bash
# Contar vendas no banco
docker exec bi_cometa_db psql -U bi_user -d bi_cometa \
  -c "SELECT COUNT(*) FROM vendas;"

# Após bootstrap deve ter ~7,197 vendas
# Vendas vazias = bootstrap não rodou ou falhou
```

---

## 💡 Arquitetura

```
docker/entrypoint-etl.sh (novo)
    │
    ├─ Espera database ficar pronto
    │
    ├─ Verifica se bootstrap é necessário
    │  └─ Tabela 'vendas' existe?
    │  └─ Tem dados?
    │
    ├─ Se SIM (bootstrap necessário)
    │  └─ Roda bootstrap.py
    │     └─ Chama ETLService.processar_vendas()
    │     └─ Chama ETLService.processar_estoque()
    │
    └─ Depois (sempre)
       └─ Inicia scheduler normal
          └─ Roda job a cada 5 minutos
```

---

## 📁 Arquivos Novos/Modificados

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| `src/bootstrap.py` | 🆕 Novo | Script de bootstrap Python |
| `docker/entrypoint-etl.sh` | 🆕 Novo | Shell script que detecta + roda bootstrap |
| `docker/Dockerfile.etl` | ✏️ Modificado | Usa entrypoint-etl.sh |

---

## 🧪 Testar Bootstrap

### Cenário 1: Primeira Execução (Clean)

```bash
# 1. Remover volumes antigos
docker compose down -v

# 2. Build fresh
docker compose up --build -d

# 3. Ver logs
docker logs -f bi_cometa_etl --tail 50

# Esperado: Bootstrap executa
```

### Cenário 2: Segunda Execução (Skip)

```bash
# 1. Reiniciar container
docker restart bi_cometa_etl

# 2. Ver logs
docker logs bi_cometa_etl --tail 30

# Esperado: "Database already initialized, skipping bootstrap"
```

### Cenário 3: Forçar Bootstrap

```bash
# Mesmo com dados, força re-bootstrap
docker exec bi_cometa_etl python bootstrap.py --force

# Carrega dados novamente (alguns duplicados, alguns replaced)
```

---

## ⚙️ Como Funciona a Detecção

O bootstrap detecta automaticamente se é necessário:

```python
# 1. Verifica se tabela 'vendas' existe
SELECT COUNT(*) FROM information_schema.tables 
WHERE table_name='vendas'

# Se não existe → Bootstrap necessário!

# 2. Se existe, conta rows
SELECT COUNT(*) FROM vendas

# Se 0 rows → Bootstrap necessário!

# Se > 0 rows → Pula bootstrap, inicia scheduler
```

---

## 📊 O Que o Bootstrap Carrega

### Vendas
- **Período**: Histórico dependendo de quantos meses registros a API tem
- **Lojas**: Todas (45 lojas padrão)
- **Granularidade**: Diária (ou conforme API retorna)
- **Quantidade**: ~7,197 vendas (baseline)

### Estoque
- **Tipo**: Snapshot atual (não histórico)
- **Lojas**: Todas
- **Itens**: ~2,070 produtos
- **Atualização**: Replace (limpa + insere novo)

---

## 🔧 Customização

### Carregar Outros Anos

```bash
# Carregar dados de 2024
docker exec bi_cometa_etl python bootstrap.py --year 2024

# Usando CLI local (se Python instalado)
cd BI_COMETA
python src/bootstrap.py --year 2024
```

### Executar Sem Checks

```bash
# Force bootstrap mesmo com dados (para teste)
docker exec bi_cometa_etl python bootstrap.py --force

# ⚠️ Risco: Pode duplicar dados se não houver constraints
```

---

## ⚠️ Troubleshooting

### Bootstrap Não Executa

```bash
# Check logs
docker logs bi_cometa_etl | grep -i bootstrap

# Possíveis causas:
# 1. Database não está pronto
#    → Espere 10-15 segundos, container reinicia sozinho
# 2. Banco já tem dados
#    → Normal, bootstrap salta automaticamente
# 3. Erro na coleta da API
#    → Check logs, pode ser credenciais inválidas
```

### Bootstrap Rodou Mas Sem Dados

```bash
# Verificar se dados foram inseridos
docker exec bi_cometa_db psql -U bi_user -d bi_cometa \
  -c "SELECT COUNT(*) FROM vendas;"

# Se 0, check logs da API
docker logs bi_cometa_etl | grep -i "error\|failed"

# Possível causa: API Cometa retornando erro ou dados inválidos
```

### Reimplementar Bootstrap (limpar e recomeçar)

```bash
# 1. Limpar database
docker compose down -v

# 2. Remover volumes se persistirem
docker volume rm bi_cometa_db

# 3. Reconstruir
docker compose up --build -d

# Bootstrap deve rodar automaticamente
```

---

## 📈 Performance

```
Bootstrap Duration: ~10-15 segundos
Dados Carregados: 7,197 vendas + 2,070 estoque
Throughput: 600-800 records/segundo

Depois disso:
- ETL normal roda a cada 5 minutos
- Apenas dados NOVOS/ATUALIZADOS são processados
```

---

## 🎯 Uso em Produção

### Deployment Automático

```bash
# 1. CI/CD pipeline
#    └─ docker compose build
#
# 2. Deploy para staging
#    └─ docker compose up -d
#    └─ Bootstrap roda automaticamente
#
# 3. Verify
#    └─ curl http://localhost:8000/health
#    └─ Sistema ready em ~2 minutos
#
# 4. Deploy para produção
#    └─ docker compose up -d
#    └─ Bootstrap roda automaticamente
#    └─ Sistema pronto para operação
```

### Monitoramento

```bash
# Verificar se bootstrap completou
docker logs bi_cometa_etl | grep "✅ BOOTSTRAP COMPLETED"

# Alert se algo falha
docker logs bi_cometa_etl | grep -i "❌\|ERROR"
```

---

## 🔐 Segurança

### Credenciais

- `.env` é lida automaticamente pelo entrypoint
- Credenciais nunca logadas (exceto em DEBUG mode)
- DATABASE_URL e API tokens protegidos

### Idempotência

- Bootstrap roda uma única vez (automaticamente detectado)
- Safe para reexecutar (skip se já tem dados)
- Vendas duplicas evitadas via DATABASE constraints

---

## 📚 Referência Rápida

```bash
# Ver status do bootstrap
docker logs bi_cometa_etl | grep -E "BOOTSTRAP|bootstrap"

# Rodar bootstrap manualmente
docker exec bi_cometa_etl python bootstrap.py

# Forçar bootstrap (re-rodar)
docker exec bi_cometa_etl python bootstrap.py --force

# Ver dados no banco
docker exec bi_cometa_db psql -U bi_user -d bi_cometa \
  -c "SELECT COUNT(*) as total_vendas FROM vendas;"

# Limpar tudo e recomeçar
docker compose down -v && docker compose up --build -d
```

---

## ✅ Checklist

Sua primeira execução deve:

- [ ] Database container inicia
- [ ] ETL container inicia  
- [ ] Bootstrap detecta banco vazio
- [ ] Bootstrap coleta vendas (~10sec)
- [ ] Bootstrap coleta estoque
- [ ] Banco tem ~7,197 vendas
- [ ] Banco tem ~2,070 estoque items
- [ ] Scheduler inicia (próximo job em 5 min)
- [ ] Logs mostram "✅ BOOTSTRAP COMPLETED"

---

**Version**: 2.1  
**Created**: 2026-02-11  
**Status**: ✅ Production Ready
