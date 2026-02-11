# BI_COMETA - Guia de Monitoramento e Observabilidade

## 📊 Dashboard de Saúde da API Cometa

Este guia fornece comandos para monitorar a qualidade dos dados e saúde da integração.

---

## 🔍 Verificações Rápidas

### 1. Status Atual (Último Job)

```bash
# Ver últimos 100 linhas do log ETL
docker logs bi_cometa_etl --tail 100

# Filtrar apenas informações de resumo
docker logs bi_cometa_etl --tail 100 | grep -E "(collection summary|ETL finished|Loja.*sucesso)"
```

**Output Esperado**:
```
Vendas collection summary: sucesso=45, falha=0, total_vendas=7197
Vendas ETL finished. Deleted=0 Inserted=7197 Total_rows=7197
```

### 2. Próxima Execução Agendada

```bash
# Modo 1: Grep para "next run"
docker logs bi_cometa_etl --tail 200 | grep "next run"

# Mode 2: Grep para "scheduled"
docker logs bi_cometa_etl --tail 200 | grep -i "scheduled\|próximo"
```

**Output Esperado**:
```
next run at: 2026-02-11 01:29:42 UTC
(em 5 minutos a partir do último job)
```

---

## ⚠️ Monitoramento de Dados Problemáticos

### 1. Detectar Inconsistências da API

```bash
# Procurar por WARNINGs de flatten
docker logs bi_cometa_etl --tail 200 | grep "flatten_vendas: item"

# Procurar por todos os WARNINGs
docker logs bi_cometa_etl --tail 200 | grep "WARNING"
```

**Output Esperado (Sucesso)**:
```
# Se nenhum output → Nenhuma inconsistência detectada
```

**Output Esperado (Alerta)**:
```
flatten_vendas: item[0] é lista vazia ou sem dict. shape=list(len=0, first_item_type=empty)
flatten_vendas: item[1] é lista vazia ou sem dict. shape=list(len=0, first_item_type=empty)
Processamento concluído com 4 items inválidos de 4. Retornando 0 vendas válidas.
```

### 2. Rastrear Lojas com Problemas

```bash
# Lojas que retornaram 0 vendas
docker logs bi_cometa_etl --tail 300 | grep "Loja.*: 0 vendas"

# Lojas com sucesso (mostra progresso)
docker logs bi_cometa_etl --tail 300 | grep "sucesso:" | tail -10
```

**Output Esperado**:
```
Loja 41: 0 vendas processadas (sucesso: 38/45)
Loja 44: 0 vendas processadas (sucesso: 42/45)
Loja 46: 0 vendas processadas (sucesso: 44/45)
```

### 3. Verificar Erros de Banco de Dados

```bash
# Procurar por ERRORs
docker logs bi_cometa_etl --tail 200 | grep "ERROR"

# Procurar por exceções
docker logs bi_cometa_etl --tail 200 | grep -E "Exception|Traceback"
```

---

## 📈 Análises Históricas

### 1. Padrões de Falha por Loja

Rastrear se as mesmas lojas falham consistentemente:

```bash
# Identificar lojas problemáticas (retorno múltiplo)
for i in {1..10}; do
  echo "=== Ciclo $i ==="
  docker logs bi_cometa_etl | grep "Loja.*: 0 vendas"
done
```

**Interpretação**:
```
Se lojas 41, 44, 46 aparecem SEMPRE com 0 vendas:
→ Problema sistemático na API para essas lojas
→ Contatar Cometa para investigação de dados

Se lojas variam cada ciclo:
→ Problema intermitente de rede/timeout
→ Considerar retry logic ou timeout maior
```

### 2. Distribuição de Vendas por Loja

```bash
# Extrair contagem de vendas por loja (último ciclo)
docker logs bi_cometa_etl --tail 300 | grep "Loja.*vendas processadas" | grep -oE "Loja [0-9]+: [0-9]+" | sort -t: -k2 -nr
```

**Output Esperado**:
```
Loja 3: 450
Loja 7: 398
Loja 15: 287
...
Loja 41: 0   <-- Alerta
Loja 44: 0   <-- Alerta
Loja 46: 0   <-- Alerta
```

### 3. Taxa de Sucesso da API

```bash
# Calcular percentual de sucesso
docker logs bi_cometa_etl --tail 100 | grep "collection summary"
# Dividir: sucesso / (sucesso + falha) * 100
```

**Cálculo**:
```
sucesso=45, falha=0
Taxa = 45/45 * 100 = 100%  ✅

sucesso=43, falha=2
Taxa = 43/45 * 100 = 95.6% ⚠️ (investigar lojas 41, 46)
```

---

## 🔧 Diagnóstico Avançado

### 1. Validar Estrutura de Resposta da API

```bash
# Testar endpoint de estoque (exemplo)
curl -X GET "http://localhost:8000/estoque" \
  -H "Authorization: Bearer seu_token"

# Verificar estrutura JSON
curl -X GET "..." | jq '.[0] | keys'
```

### 2. Comparar Schemas

```bash
# Verificar schema esperado vs recebido
python3 << 'EOF'
from App.core.schemas import VendaSchema
from pprint import pprint

# Schema esperado
print("Campos esperados (VendaSchema):")
pprint(VendaSchema.model_fields.keys())

# Testar validação
try:
    v = VendaSchema(LOJA=3, DATA="2026-01-01", PRODUTO="X", QTD=5)
    print("\n✅ Validação bem-sucedida")
except Exception as e:
    print(f"\n❌ Erro: {e}")
EOF
```

### 3. Executar Job Manualmente

```bash
# Forçar execução do ETL (não esperar 5 minutos)
docker exec bi_cometa_etl python3 -c "
import sys
sys.path.insert(0, '/app')
from App.etl.etl_service import ETLService
from config import Settings

settings = Settings()
service = ETLService(settings)
service.executar()
"
```

---

## 📋 Checklist de Status

Execute este comando para verificação rápida:

```bash
echo "=== HEALTH CHECKS ==="
curl -s http://localhost:8000/health | jq .

echo -e "\n=== DB STATUS ==="
curl -s http://localhost:8000/health/db | jq .

echo -e "\n=== LAST ETL RUN ==="
docker logs bi_cometa_etl --tail 50 | grep -E "(ETL Job Completed|collection summary)"

echo -e "\n=== NEXT SCHEDULED RUN ==="
docker logs bi_cometa_etl --tail 50 | grep "next run"

echo -e "\n=== ALERTS ==="
docker logs bi_cometa_etl --tail 100 | grep -E "(WARNING|ERROR)" | head -5
```

---

## 🚨 Alertas e Ações

### Alerta 1: Múltiplas Lojas com 0 Vendas

```
Indicador: Loja 41, 44, 46 sempre retornam 0 vendas
Causa Provável: API retorna listas vazias para essas lojas
Ação:
  1. Verificar se lojas existem no sistema Cometa
  2. Validar permissões de acesso
  3. Contatar Cometa: "Lojas 41, 44, 46 retornam dados vazios"
```

### Alerta 2: Taxa de Sucesso < 95%

```
Indicador: sucesso < 90% do total de lojas
Causa Provável: Timeout ou erro de conexão
Ação:
  1. Verificar status da rede
  2. Aumentar timeout em api_cometa.py
  3. Revisar logs de conexão: docker logs bi_cometa_etl --tail 500 | grep -i timeout
```

### Alerta 3: Total de Vendas Diminuiu > 10%

```
Indicador: Semana anterior: 7197 vendas, esta semana: 6000 vendas
Causa Provável: API mudança, lojas desativadas ou erro em coleta
Ação:
  1. Verificar lojas com 0 vendas (vs semana anterior)
  2. Revisar se API Cometa teve mudanças
  3. Verificar se houve downtime do container ETL
```

### Alerta 4: ETL Não Executa por 10+ Minutos

```
Indicador: Último log > 10 minutos atrás
Causa Provável: Container travado ou scheduler parou
Ação:
  1. Verificar status: docker ps | grep bi_cometa_etl
  2. Ver logs de erro: docker logs bi_cometa_etl --tail 100
  3. Reiniciar se necessário: docker restart bi_cometa_etl
```

---

## 📊 Métricas Recomendadas para Dashboard

Se estiver usando Prometheus/Grafana, coletar:

```python
# Métrica 1: Taxa de sucesso por ciclo
etl_lojas_sucesso{ciclo="2026-02-11T01:24"}  45
etl_lojas_falha{ciclo="2026-02-11T01:24"}     0

# Métrica 2: Vendas processadas
etl_vendas_total{ciclo="2026-02-11T01:24"}  7197
etl_vendas_insertadas{ciclo="2026-02-11T01:24"}  7197

# Métrica 3: Duração do job
etl_duration_seconds{ciclo="2026-02-11T01:24"}  10.75

# Métrica 4: Items inválidos detectados
etl_invalid_items{ciclo="2026-02-11T01:24", tipo="venda"}  4
etl_invalid_items{ciclo="2026-02-11T01:24", tipo="estoque"}  0
```

---

## 🔄 Rotina Diária Recomendada

```bash
#!/bin/bash
# run_daily_check.sh

echo "=== BI_COMETA Daily Health Check $(date) ==="

# 1. Verificar se containers estão rodando
echo -e "\n1. Container Status:"
docker ps | grep bi_cometa

# 2. Verificar última execução
echo -e "\n2. Last ETL Execution:"
docker logs bi_cometa_etl --tail 3 | grep -E "(ETL Job Completed|next run)"

# 3. Verificar taxa de sucesso
echo -e "\n3. Success Rate:"
docker logs bi_cometa_etl --tail 50 | grep "collection summary"

# 4. Verificar alertas
echo -e "\n4. Recent Alerts (last 12 hours):"
docker logs bi_cometa_etl --since 12h | grep -E "(WARNING|ERROR)" | wc -l
echo "   Details:"
docker logs bi_cometa_etl --since 12h | grep -E "(WARNING|ERROR)" | head -5

# 5. API Health
echo -e "\n5. API Health:"
curl -s http://localhost:8000/health | jq '.status' || echo "OFFLINE"

# 6. Database Status
echo -e "\n6. Database Health:"
curl -s http://localhost:8000/health/db | jq '.status' || echo "OFFLINE"

echo -e "\n=== End of Report ==="
```

Salvar como `check_health.sh` e executar diariamente:
```bash
chmod +x check_health.sh
./check_health.sh > health_$(date +%Y%m%d).log
```

---

## 🎯 Próximos Passos

- [ ] Desenvolver alert script para notificar via Slack/Email
- [ ] Criar dashboard Grafana com métricas
- [ ] Implementar log aggregation (ELK Stack)
- [ ] Adicionar health endpoint para ETL service
- [ ] Documentar runbook para escalação

Última Atualização: 2026-02-11
