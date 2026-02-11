# Desenho do Banco de Dados

## Visão Geral

O database é estruturado em **2 tabelas principais** com dados **normalizados e sem JSONB**:
- `vendas`: Registro transacional de cada venda (linha)
- `estoque`: Snapshot atual de estoque por loja e produto

## Tabela: `vendas`

Registro individual de cada produto vendido em uma transação.

```sql
CREATE TABLE vendas (
    id                SERIAL PRIMARY KEY,
    data              DATE NOT NULL,
    loja_id           INTEGER NOT NULL,
    nome_loja         VARCHAR(255),
    cnpj_loja         VARCHAR(18),
    ean               VARCHAR(20),
    cod_interno       VARCHAR(50),
    plu               INTEGER,
    produto           VARCHAR(500),
    qtd               FLOAT NOT NULL DEFAULT 0.0,
    venda             FLOAT NOT NULL DEFAULT 0.0,
    custo             FLOAT NOT NULL DEFAULT 0.0,
    created_at        DATETIME NOT NULL DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_vendas_data ON vendas(data DESC);
CREATE INDEX idx_vendas_loja_id ON vendas(loja_id);
CREATE INDEX idx_vendas_data_loja ON vendas(data, loja_id);
```

**Cardinalidade**: 
- Volta a 0 a cada mês (UPSERT deleta tudo do mês, insere novo)
- ~3-5k vendas/loja/mês (depende do volume)

**Acesso**:
- `/api/v1/vendas`: ORDER BY data DESC, id DESC
- Sem paginação (retorna todas as linhas)

---

## Tabela: `estoque`

Snapshot atual (mais recente) de estoque por loja e produto.

```sql
CREATE TABLE estoque (
    id                    SERIAL PRIMARY KEY,
    snapshot_ts           DATETIME NOT NULL DEFAULT NOW(),
    loja_id               INTEGER NOT NULL,
    codigo_produto        VARCHAR(50) NOT NULL,
    descricao_produto     VARCHAR(500) NOT NULL,
    ean                   VARCHAR(20),
    estq_loja             INTEGER NOT NULL DEFAULT 0,
    estq_avaria           INTEGER NOT NULL DEFAULT 0
);

-- Índices para performance
CREATE INDEX idx_estoque_snapshot_ts ON estoque(snapshot_ts DESC);
CREATE INDEX idx_estoque_loja ON estoque(loja_id);
CREATE INDEX idx_estoque_codigo ON estoque(codigo_produto);
```

**Cardinalidade**:
- Volta a 0 a cada ETL (REPLACE deleta tudo, insere novo)
- ~300-500 produtos/loja (depende do catálogo)

**Acesso**:
- `/api/v1/estoque`: ORDER BY snapshot_ts DESC, loja_id, codigo_produto
- Sem paginação (retorna todas as linhas)

---

## Transformação de Dados

### Entrada (API Cometa)

**Vendas (Nested)**:
```json
{
  "LOJA": {
    "LOJA": 3,
    "NOME": "03- OL PAIVA",
    "CNPJ": "06887668000340"
  },
  "VENDAS": [
    {
      "LOJA": 3,
      "DATA": "01/12/2025",
      "EAN": "7898200380953",
      "COD_INTERNO": "142289",
      "PLU": 142289,
      "PRODUTO": "Iog Vale Milk...",
      "QTD": 6,
      "VENDA": 22.74,
      "CUSTO": 2.65
    },
    ...
  ]
}
```

**Estoque (Quasi-flat)**:
```json
{
  "LOJA": 1,
  "CODIGO_PRODUTO": "142289",
  "DESCRICAO_PRODUTO": "Iog Vale Milk Bicamada 130G Morango",
  "EAN": "7898200380953",
  "ESTQ_LOJA": 27,
  "ESTQ_AVARIA": 4
}
```

### Transformação

1. **Flatten Vendas** (`App/shared/utils.py::flatten_vendas`):
   - Extrai `NOME_LOJA` e `CNPJ_LOJA` do dict `LOJA`
   - Desplaniifica array `VENDAS` → cada item = 1 linha
   - Resultado: Lista de dicts **planos** com 1 venda por linha

2. **Flatten Estoque** (`App/shared/utils.py::flatten_estoque`):
   - Padroniza chaves (UPPERCASE)
   - Garante presença de colunas obrigatórias
   - Resultado: Lista de dicts **planos** com 1 produto/loja por linha

3. **Inserção** (`App/core/database.py::_prepare_*_rows`):
   - Extrai/converte tipos (datas, ints, floats)
   - Valida campos obrigatórios
   - Insere direto nas colunas apropriadas (SEM JSONB)

### Saída (API FastAPI)

**Vendas**:
```json
[
  {
    "id": 123,
    "data": "2025-12-01",
    "loja_id": 3,
    "nome_loja": "03- OL PAIVA",
    "cnpj_loja": "06887668000340",
    "ean": "7898200380953",
    "cod_interno": "142289",
    "plu": 142289,
    "produto": "Iog Vale Milk Bicamada 130G Morango",
    "qtd": 6.0,
    "venda": 22.74,
    "custo": 2.65,
    "created_at": "2025-02-10T10:30:00"
  },
  ...
]
```

**Estoque**:
```json
[
  {
    "id": 456,
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

---

## Fluxo ETL

### Vendas
```
1. CometaClient.get_vendas_loja()
   └─ API retorna dados NESTED

2. flatten_vendas()
   └─ Desplaniifica → lista de dicts planos

3. DatabaseClient.upsert_vendas()
   ├─ DELETE FROM vendas WHERE data BETWEEN min_date AND max_date
   └─ INSERT INTO vendas (data, loja_id, nome_loja, ...)

4. API: SELECT * FROM vendas ORDER BY data DESC, id DESC
```

### Estoque
```
1. CometaClient.get_estoque()
   └─ API retorna dados quasi-flat

2. flatten_estoque()
   └─ Padroniza chaves → lista de dicts planos

3. DatabaseClient.replace_estoque()
   ├─ DELETE FROM estoque  (limpa TUDO)
   └─ INSERT INTO estoque (snapshot_ts, loja_id, codigo_produto, ...)

4. API: SELECT * FROM estoque ORDER BY snapshot_ts DESC, loja_id, codigo_produto
```

---

## Performance

| Operação | Índice | Complexidade |
|----------|--------|--------------|
| `fetch_vendas()` | `(data DESC, id)` | O(1) + sequential scan |
| `fetch_estoque()` | `(snapshot_ts DESC)` | O(1) + sequential scan |
| `upsert_vendas()` | `(data)` para delete | O(log n) delete + O(1) insert |
| `replace_estoque()` | Full table | O(n) delete + O(m) insert |

**Sem paginação**:
- Dados retornam conforme consumidor lê (streaming)
- Ideal para BI (ferramentas costumam carregar tudo)
- Banco mantém índices para ordenação rápida

---

## Considerações de Design

1. **Sem JSONB**: Todos vs. dados estruturados
   - ✓ Melhor performance em queries
   - ✓ Type safety
   - ✓ Facilita índices
   - ✓ Legível em `SELECT *`

2. **UPSERT (não UPDATE)**: Vendas por período
   - Idempotente: rodar 2x = mesmo resultado
   - Simples: delete tudo do período, insere novo
   - Seguro: sem race conditions parciais

3. **REPLACE (não incremental)**: Estoque
   - Snapshot sempre reflete realidade atual
   - Sem dados órfãos ou desincronizados
   - Simples de entender

4. **Sem paginação**: API
   - Consumidor (BI) espera dados completos
   - FastAPI retorna JSON em streaming
   - Índices garantem ordering rápido
