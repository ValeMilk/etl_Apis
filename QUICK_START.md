# Quick Start - BI_COMETA

## 1. Pré-requisitos

- Docker + Docker Compose (recomendado)
- OU: Python 3.10+, PostgreSQL 15+

## 2. Setup Rápido (Docker)

```bash
# Clonar/abrir projeto
cd BI_COMETA

# Copiar .env
cp .env.example .env

# Editar .env com credenciais reais
nano .env
# Altere:
# API_BASE_URL=https://...
# API_EMAIL=seu_email
# API_PASSWORD=sua_senha

# Subir containers
docker compose -f docker/docker-compose.yml up --build

# Aguardar ~30s para banco iniciar

# Em outro terminal, teste
curl http://localhost:8000/health          # Health check
curl http://localhost:8000/api/v1/vendas  # Vendas (vazio no início)
curl http://localhost:8000/api/v1/estoque # Estoque (vazio no início)
```

A primeira execução do ETL ocorre 1 hora após startup (configurável).

## 3. Setup Manual (Desenvolvimento)

```bash
# Ambiente Python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependências
pip install -r requirements.txt

# Database (inicie PostgreSQL)
# Linux/Mac:
#   brew install postgresql
#   brew services start postgresql
# Windows:
#   Instale PostgreSQL via MSI, inicie pgAdmin ou `net start postgresql-x64-15`

# Criar banco
psql -U postgres -c "CREATE DATABASE bi_cometa;"
psql -U postgres -d bi_cometa -c "CREATE USER bi_user WITH PASSWORD 'bi_password';"
psql -U postgres -d bi_cometa -c "GRANT ALL PRIVILEGES ON DATABASE bi_cometa TO bi_user;"

# Variáveis de ambiente
cp .env.example .env
nano .env  # Editar com credenciais
source .env  # (ou export...)

# Iniciar servidor
cd src
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 4. Validar Setup

```bash
# Health check
curl -s http://localhost:8000/health | jq

# Deve retornar:
# {
#   "status": "ok",
#   "version": "1.0.0"
# }

# Logs (deve mostrar inicialização)
# 2025-02-10 10:30:00,123 | INFO     | Main                  | BI_COMETA Starting...
# 2025-02-10 10:30:00,456 | INFO     | Main                  | Configuration validated
# ...
# 2025-02-10 10:30:01,789 | INFO     | Main                  | Scheduler started with 2 jobs
```

## 5. Forçar Primeira Execução (Opcional)

Ao invés de aguardar 1h, você pode forçar o ETL via Python:

```bash
python -c "
from main import etl_service
print('Executando ETL...')
etl_service.processar_estoque()
print('Estoque processado')
etl_service.processar_vendas()
print('Vendas processadas')
"
```

## 6. Consumir Dados

```bash
# Vendas (sem paginação)
curl -s http://localhost:8000/api/v1/vendas | jq '.[0]'

# Retorna primeira venda:
# {
#   "id": 1,
#   "data": "2025-12-01",
#   "loja_id": 3,
#   "nome_loja": "03- OL PAIVA",
#   "produto": "Iog Vale Milk...",
#   "qtd": 6.0,
#   "venda": 22.74,
#   "custo": 2.65,
#   ...
# }

# Estoque (sem paginação)
curl -s http://localhost:8000/api/v1/estoque | jq '.[0]'

# Retorna primeiro item:
# {
#   "id": 1,
#   "snapshot_ts": "2025-02-10T10:30:00",
#   "loja_id": 1,
#   "codigo_produto": "142289",
#   "descricao_produto": "Iog Vale Milk...",
#   "estq_loja": 27,
#   "estq_avaria": 4
# }
```

## 7. Integração com BI

Qualquer ferramenta pode consumir:

```bash
# Power BI, Tableau, etc.
GET http://localhost:8000/api/v1/vendas    # JSON completo
GET http://localhost:8000/api/v1/estoque   # JSON completo

# Exportar para CSV
curl -s http://localhost:8000/api/v1/vendas | jq -r '
  (.[0] | keys_unsorted) as $keys |
  ($keys | @csv), 
  (.[] | [$keys[] as $k | .[$k]] | @csv)
' > vendas.csv

# Usee pandas para transformar
python -c "
import requests
import pandas as pd

vendas = requests.get('http://localhost:8000/api/v1/vendas').json()
df = pd.DataFrame(vendas)
df.to_csv('vendas.csv', index=False)
print(f'Exportadas {len(df)} vendas')
"
```

## 8. Troubleshooting

### "Connection refused" (banco não conecta)
```bash
# Verificar se PostgreSQL está rodando
docker ps  # procure postgres:15
# ou
psql -U postgres -c "SELECT 1"  # deve retornar 1

# Reiniciar container
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up --build
```

### "Invalid credentials" (API não autentica)
```bash
# Validar credenciais em .env
cat .env | grep API_

# Testar com curl
curl -X POST https://vendas.cometasupermercados.com.br/login \
  -H "Content-Type: application/json" \
  -d '{"email":"seu_email","password":"sua_senha"}'
# Deve retornar token string
```

### "No lojas found" (ETL não busca dados)
```bash
# Esperar 1h ou forçar conforme seção 5
# Validar logs em main.py

# Checar banco
docker exec BI_COMETA-db-1 psql -U bi_user -d bi_cometa -c "SELECT COUNT(*) FROM estoque;"

# Se retorna 0, ETL não executou ainda
```

### "No vendas fetched" (dados vazios)
- Normal se API retorna sem dados para o período
- Validar datas em logs
- Testar `/api/v1/estoque` primeiro (estoque é pré-requisito)

## 9. Próximas Etapas

1. **Validar dados**: Execute ETL e verifique `/health` + `/api/v1/*`
2. **Integrar BI**: Aponte Power BI ou Tableau para os endpoints
3. **Monitorar**: Observe logs em `docker logs BI_COMETA-app-1`
4. **Customizar**: Ajuste `ETL_INTERVAL_HOURS` em `.env` se necessário

## 10. Documentação Completa

- [README.md](README.md): Visão geral e arquitetura
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md): Estrutura de dados e transformações
- [Dockerfile](docker/Dockerfile): Imagem Docker
- [docker-compose.yml](docker/docker-compose.yml): Orquestração
