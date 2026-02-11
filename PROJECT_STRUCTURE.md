BI_COMETA/
├── .env                           # Variáveis de ambiente (não versionado)
├── .env.example                   # Exemplo de variáveis de ambiente
├── .gitignore                     # Arquivos ignorados por git
├── README.md                      # Documentação principal
├── QUICK_START.md                # Guia de início rápido
├── DATABASE_DESIGN.md            # Design do banco de dados
├── requirements.txt              # Dependências Python
│
├── src/
│   ├── __init__.py
│   ├── main.py                   # Entrypoint (FastAPI + APScheduler)
│   ├── api_cometa.py             # Cliente HTTP para API Cometa
│   │
│   └── App/
│       ├── __init__.py
│       │
│       ├── core/                 # Camada de dados e configuração
│       │   ├── __init__.py
│       │   ├── config.py         # Configurações centralizadas
│       │   ├── database.py       # SQLAlchemy client + definição de tabelas
│       │   └── models.py         # Schema de dados (dataclasses)
│       │
│       ├── etl/                  # Orquestração de dados
│       │   ├── __init__.py
│       │   └── etl_service.py    # ETL service (vendas + estoque)
│       │
│       ├── api/                  # Rotas API FastAPI
│       │   ├── __init__.py
│       │   └── routes.py         # Endpoints /api/v1/*
│       │
│       └── shared/               # Utilitários compartilhados
│           ├── __init__.py
│           └── utils.py          # Funções de transformação, parsing, etc
│
├── docker/
│   ├── Dockerfile                # Imagem Python 3.10-slim
│   └── docker-compose.yml        # Orquestração (app + postgres)
│
└── tests/
    ├── __init__.py
    └── test_flatten.py           # Testes de desplanificação de dados


RESPONSABILIDADES POR MÓDULO
============================

api_cometa.py
  - Autentica na API externa
  - Busca estoque (lista de produtos)
  - Busca vendas por loja e período
  - Valida credenciais e timeouts
  → Retorna dados DESPLANIFICADOS (lista de dicts planos)

App/core/config.py
  - Centraliza variáveis de ambiente
  - Valida configuração obrigatória
  - Fornece defaults sensatos

App/core/database.py
  - Define tabelas vendas + estoque via SQLAlchemy
  - Gerencia sessões de banco
  - Prepara linhas para inserção
  - Executa upserts de forma segura
  - Retorna dados como dicts serializáveis

App/core/models.py
  - Define schemas de dados (dataclasses)
  - Tipagem e documentação
  - (Opcional: validação com Pydantic)

App/shared/utils.py
  - flatten_vendas(): desplaniifica dados aninhados
  - flatten_estoque(): padroniza chaves
  - parse_date(): parse de múltiplos formatos
  - safe_int/safe_float: conversões seguras

App/etl/etl_service.py
  - Orquestra ETL end-to-end
  - Busca lojas via CometaClient
  - Paralela fetches de vendas (ThreadPoolExecutor)
  - Upserta dados no banco
  - Logging de progresso

App/api/routes.py
  - Define rotas FastAPI
  - Chamadas diretas ao DatabaseClient
  - Retorna JSON sem paginação
  - Logging de requisições

main.py
  - Carrega .env
  - Configura logging
  - Instancia clientes (Cometa, Database, ETL)
  - Inicializa FastAPI
  - Inicia agendador (APScheduler) no startup
  - Para agendador no shutdown
  - Health check simples

tests/test_flatten.py
  - Valida desplanificação de dados
  - Testa conversões de tipo
  - Executa localmente ou em CI/CD


FLUXO DE DADOS
==============

[API Cometa]
    ↓
[CometaClient.get_estoque/get_vendas()]  (dados brutos, alguns aninhados)
    ↓
[flatten_estoque/flatten_vendas()]       (dados PLANOS, colunas normalizadas)
    ↓
[ETLService.processar_estoque/vendas()]  (coordena busca e inserção)
    ↓
[DatabaseClient.replace_estoque/upsert_vendas()]  (prepara e insere no banco)
    ↓
[PostgreSQL]  (tabelas estruturadas: vendas + estoque)
    ↓
[DatabaseClient.fetch_vendas/estoque()]  (SELECT com índices)
    ↓
[FastAPI routes]  (retorna JSON sem paginação)
    ↓
[Consumer (BI, curl, etc)]


AGENDAMENTO (APScheduler)
=========================

Inicia no event startup com 2 jobs:
  1. etl_service.processar_estoque()  → a cada 1h (snapshot)
  2. etl_service.processar_vendas()   → a cada 1h (mês atual)

Configurável via ETL_INTERVAL_HOURS=1 em .env


ÍNDICES (PostgreSQL)
====================

vendas:
  - idx_vendas_data: (data DESC) para fetch rápido
  - idx_vendas_loja_id: (loja_id) para queries por loja
  - idx_vendas_data_loja: (data, loja_id) para BETWEEN em upsert

estoque:
  - idx_estoque_snapshot_ts: (snapshot_ts DESC) para snapshot atual
  - idx_estoque_loja: (loja_id) para queries por loja
  - idx_estoque_codigo: (codigo_produto) para lookups de produto


SEGURANÇA
=========

✓ Credenciais em .env (nunca commitar)
✓ SQL Injection: SQLAlchemy com prepared statements
✓ Transações atômicas: contexto get_session() com rollback
✓ SSL desabilitado por padrão (VERIFY_SSL=false) - ajuste em produção
✓ Validação de tipos: safe_int, safe_float
✓ Logging sem credenciais sensíveis
