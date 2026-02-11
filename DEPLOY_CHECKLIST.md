## ✅ Checklist de Deploy - BI_COMETA

Use este checklist para validar o setup completo antes de considerar o sistema pronto.

---

### 🔧 Pré-requisitos

- [ ] Docker + Docker Compose instalados
  ```bash
  docker --version
  docker-compose --version
  ```

- [ ] Python 3.10+ (se setup manual)
  ```bash
  python --version  # deve ser 3.10+
  ```

- [ ] PostgreSQL 15 (via Docker ou local)
  ```bash
  # Se Docker:
  docker ps | grep postgres
  ```

---

### 📋 Configuração

- [ ] `.env` criado a partir de `.env.example`
  ```bash
  ls -la .env  # deve existir
  ```

- [ ] Variáveis críticas preenchidas
  ```bash
  grep "^API_EMAIL\|^API_PASSWORD\|^DB_URL" .env
  # Todos devem ter valores (não deve estar vazio)
  ```

- [ ] `.env` não versionado
  ```bash
  git status | grep -c ".env"
  # Deve retornar 0 (arquivo não está em staging)
  ```

---

### 🐳 Docker

- [ ] Imagem construída
  ```bash
  docker images | grep bi_cometa
  # Deve aparecer
  ```

- [ ] Containers em execução
  ```bash
  docker ps | grep -E "bi_cometa|postgres"
  # Deve aparecer pelo menos 2 containers
  ```

- [ ] PostgreSQL respondendo
  ```bash
  docker exec <container_postgres> psql -U bi_user -d bi_cometa -c "SELECT 1;"
  # Deve retornar: 1
  ```

- [ ] Aplicação iniciou sem erros
  ```bash
  docker logs <container_app> | tail -20
  # Deve mostrar: "Scheduler started with 2 jobs"
  ```

---

### 🌐 API Básica

- [ ] Health Check
  ```bash
  curl http://localhost:8000/health
  # Deve retornar:
  # {"status":"ok","version":"1.0.0"}
  ```

- [ ] App respondendo (sem dados ainda é OK)
  ```bash
  curl http://localhost:8000/api/v1/vendas
  # Pode retornar [] (lista vazia) - é esperado se ETL não rodou
  ```

- [ ] Estoque respondendo
  ```bash
  curl http://localhost:8000/api/v1/estoque
  # Pode retornar [] (lista vazia) - é esperado se ETL não rodou
  ```

---

### 🔄 ETL & Dados

**Opção A: Esperar agendador (1 hora)**
```bash
sleep 3600
curl http://localhost:8000/api/v1/vendas | jq '.[] | length'
# Deve retornar > 0
```

**Opção B: Forçar execução (recomendado para teste)**
```bash
docker exec <container_app> python -c "
from main import etl_service
print('=== Estoque ===')
etl_service.processar_estoque()
print('=== Vendas ===')
etl_service.processar_vendas()
print('=== Concluído ===')
"
```

- [ ] Estoque populado após ETL
  ```bash
  curl http://localhost:8000/api/v1/estoque | jq '. | length'
  # Deve retornar > 0 (número de produtos)
  ```

- [ ] Vendas populadas após ETL
  ```bash
  curl http://localhost:8000/api/v1/vendas | jq '. | length'
  # Deve retornar > 0 (número de vendas)
  ```

- [ ] Dados possuem campos esperados
  ```bash
  curl http://localhost:8000/api/v1/vendas | jq '.[0] | keys'
  # Deve incluir: data, loja_id, nome_loja, produto, qtd, venda, custo
  ```

---

### 📊 Validação de Dados

- [ ] Estoque tem colunas corretas
  ```bash
  curl http://localhost:8000/api/v1/estoque | jq '.[0]'
  # Deve ter: id, snapshot_ts, loja_id, codigo_produto, descricao_produto, ean, estq_loja, estq_avaria
  ```

- [ ] Vendas tem colunas corretas
  ```bash
  curl http://localhost:8000/api/v1/vendas | jq '.[0]'
  # Deve ter: id, data, loja_id, nome_loja, cnpj_loja, ean, cod_interno, plu, produto, qtd, venda, custo, created_at
  ```

- [ ] Dados não estão aninhados
  ```bash
  curl http://localhost:8000/api/v1/vendas | jq '.[0].LOJA'
  # Deve retornar null (não é dict aninhado!)
  ```

- [ ] Sem arrays dentro de vendas
  ```bash
  curl http://localhost:8000/api/v1/vendas | jq '.[0].VENDAS'
  # Deve retornar null (não há arrays aninhados!)
  ```

---

### 📝 Logging

- [ ] Logs aparecem no stdout sem erros críticos
  ```bash
  docker logs <container_app> --tail 50 | grep -i "error\|exception\|invalid"
  # Se retornar algo, investigar!
  ```

- [ ] ETL está sendo agendado
  ```bash
  docker logs <container_app> | grep "Scheduler started"
  # Deve aparecer durante startup
  ```

- [ ] Requisições sendo loggadas
  ```bash
  docker logs <container_app> --tail 5 | grep "GET /api"
  # Deve aparecer depois de chamar curl
  ```

---

### 🔗 Integração com BI (Opcional, mas Importante)

**Power BI ou Tableau**:
- [ ] Conectar a `http://localhost:8000/api/v1/vendas`
- [ ] Conectar a `http://localhost:8000/api/v1/estoque`
- [ ] Dados carregam sem erro (timeout > 60s)
- [ ] Visualizações básicas funcionam

**Python/Pandas** (Quick test):
```python
import requests
import pandas as pd

vendas = requests.get('http://localhost:8000/api/v1/vendas').json()
df = pd.DataFrame(vendas)
print(df.shape)  # Deve mostrar (linhas, 13 colunas)
print(df.dtypes) # Verificar tipos
```

- [ ] DataFrame carrega sem erros
- [ ] Nenhuma coluna é dict/list (tudo escalar)

---

### 🔐 Segurança

- [ ] `.env` NÃO versionado em git
  ```bash
  git status | grep ".env"
  # Não pode aparecer
  ```

- [ ] `.gitignore` incluir `.env`
  ```bash
  grep "^.env" .gitignore
  # Deve retornar ".env"
  ```

- [ ] Credenciais não aparecem em logs
  ```bash
  docker logs <container_app> | grep -i "password\|email\|token"
  # Não deve aparecer senhas!
  ```

---

### 📦 Documentação

- [ ] README.md existe e descreve o projeto
  ```bash
  [ -f README.md ] && echo "OK" || echo "MISSING"
  ```

- [ ] QUICK_START.md contém instruções
  ```bash
  [ -f QUICK_START.md ] && echo "OK" || echo "MISSING"
  ```

- [ ] DATABASE_DESIGN.md documenta schema
  ```bash
  [ -f DATABASE_DESIGN.md ] && echo "OK" || echo "MISSING"
  ```

- [ ] PROJECT_STRUCTURE.md descreve organização
  ```bash
  [ -f PROJECT_STRUCTURE.md ] && echo "OK" || echo "MISSING"
  ```

---

### 🚀 Performance (Spot Check)

- [ ] `/health` responde em < 100ms
  ```bash
  time curl -s http://localhost:8000/health > /dev/null
  ```

- [ ] `/api/v1/vendas` responde em < 2s (mesmo com muitos dados)
  ```bash
  time curl -s http://localhost:8000/api/v1/vendas | jq '. | length'
  ```

- [ ] `/api/v1/estoque` responde em < 2s
  ```bash
  time curl -s http://localhost:8000/api/v1/estoque | jq '. | length'
  ```

---

### 🛑 Troubleshooting (Se algo falhar)

| Problema | Solução |
|----------|---------|
| **Connection refused** | `docker ps` - PostgreSQL rodando? |
| **Invalid credentials** | Validar API_EMAIL/PASSWORD em `.env` |
| **No estoque fetched** | Aguardar ETL (1h) ou forçar conforme seção acima |
| **Empty databases** | Rodar ETL manualmente (ver seção "ETL & Dados") |
| **Slow queries** | Verificar índices: `docker exec ... psql ... \d vendas` |
| **Logs showing errors** | `docker logs <container> \| tail -50` para contexto |

---

### ✅ Checklist Final de Deploy

```
[ ] Todos os pré-requisitos OK
[ ] Configuração (.env) completa
[ ] Docker containers rodando
[ ] PostgreSQL respondendo
[ ] API responde (/health)
[ ] ETL executou (dados existem)
[ ] Dados estruturados (sem JSONB, sem arrays aninhados)
[ ] Sem erros críticos nos logs
[ ] .env não versionado
[ ] Documentação presente
[ ] Performance aceitável
[ ] Pronto para BI consumir!
```

---

## 📞 Suporte

Se algo not working:
1. Verifique logs: `docker logs <container>`
2. Valide .env: `cat .env | grep -v "^#"`
3. Teste conexão DB: `docker exec <postgres> psql -U bi_user -d bi_cometa -c "SELECT 1;"`
4. Consulte QUICK_START.md section "Troubleshooting"

✅ **Sistema está PRONTO quando toda a checklist está marcada!**
