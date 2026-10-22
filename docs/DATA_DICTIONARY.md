# Dicionário de Dados — PostgreSQL (bi_cometa)

> Gerado a partir do schema real em `src/App/core/database.py` (fonte da verdade — as
> tabelas são criadas via `MetaData.create_all()`, sem Alembic/migrations). Se o schema
> mudar, atualize este arquivo junto.
>
> Nenhuma tabela tem foreign key formal entre si — o banco é deliberadamente flat (sem
> JSONB), e os relacionamentos (ex: `vendas.cod_interno` ↔ `estoque.codigo_produto`) são
> lógicos, resolvidos nas consultas, não por constraint.

## Visão geral das 8 tabelas

| Tabela | Fonte | Estratégia de carga | Job responsável |
|---|---|---|---|
| `vendas` | API Cometa (ValeMilk) | Delete por range de `data` + insert | `run_vendas_estoque_job` (05:00 diário) |
| `estoque` | API Cometa (ValeMilk) | Replace total (delete tudo + insert) | `run_vendas_estoque_job` (05:00 diário) |
| `vendas_valefish` | API Cometa (ValeFish) | Delete por range de `data` + insert | `run_vendas_estoque_job` (05:00 diário) |
| `estoque_valefish` | API Cometa (ValeFish) | Replace total | `run_vendas_estoque_job` (05:00 diário) |
| `infomarket` | API InfoMarket Pesquisa | TRUNCATE + insert em lote (full reload) | `run_infomarket_job` (00h/12h/16h) |
| `ativmob_estoque` | API ATIVMOB (fila + ACK) | Insert append-only, dedupe por `event_id` | `run_ativmob_job` (00:15/12:15/16:15) |
| `ativmob_agendamentos` | API ATIVMOB (consulta) | Delete por `origem` + insert (replace parcial) | `run_ativmob_agendamentos_job` (05:30 diário) |
| `ativmob_km` | API ATIVMOB (fila + ACK) | Insert append-only, dedupe por `event_id` | `run_ativmob_km_job` (00:25/12:25/16:25) |

---

## `vendas`

Vendas do ValeMilk, uma linha por venda individual. Volta a zero por período a cada carga
(`DELETE WHERE data BETWEEN min, max` do lote recebido, depois `INSERT`).

| Coluna | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | não | PK autoincrement |
| `data` | DATE | não | Data da venda |
| `loja_id` | INTEGER | não | ID da loja na Cometa |
| `nome_loja` | VARCHAR(255) | sim | Nome da loja |
| `cnpj_loja` | VARCHAR(18) | sim | CNPJ da loja |
| `ean` | VARCHAR(20) | sim | Código de barras. **Sempre `NULL`** — a API às vezes manda múltiplos EANs colados (`"cod1,cod2"`), o que já estourou a coluna; não é usado pelo BI, então o pipeline parou de gravar valor nenhum aqui |
| `cod_interno` | VARCHAR(50) | sim | Código interno do produto (chave de join com `estoque.codigo_produto`) |
| `plu` | INTEGER | sim | PLU do produto |
| `produto` | VARCHAR(500) | sim | Descrição do produto |
| `qtd` | FLOAT | não | Quantidade vendida |
| `venda` | FLOAT | não | Valor de venda |
| `custo` | FLOAT | não | Valor de custo |
| `created_at` | TIMESTAMP | não | Quando a linha foi gravada |

## `estoque`

Snapshot atual de estoque do ValeMilk (não é histórico — cada carga apaga tudo e reinsere
o estado mais recente).

| Coluna | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | não | PK autoincrement |
| `snapshot_ts` | TIMESTAMP | não | Quando o snapshot foi tirado |
| `loja_id` | INTEGER | não | ID da loja |
| `codigo_produto` | VARCHAR(50) | não | Código do produto (chave de join com `vendas.cod_interno`) |
| `descricao_produto` | VARCHAR(500) | não | Descrição do produto |
| `ean` | VARCHAR(20) | sim | Código de barras (mesma ressalva de `vendas.ean`: sempre `NULL`) |
| `estq_loja` | INTEGER | não | Quantidade em estoque na loja |
| `estq_avaria` | INTEGER | não | Quantidade avariada |

## `vendas_valefish` / `estoque_valefish`

Mesma estrutura e mesmas regras de `vendas`/`estoque` acima — é a segunda conta Cometa
(ValeFish), com tabelas espelhadas em vez de uma coluna discriminadora.

## `infomarket`

Encartes/preços de concorrentes, recarregados do zero 3x/dia (`TRUNCATE` + insert — não é
delete por período, é a tabela inteira).

| Coluna | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | não | PK autoincrement |
| `price_id` | VARCHAR(50) | não | ID do preço na InfoMarket |
| `item_id` | VARCHAR(50) | sim | ID do item/produto |
| `description` | VARCHAR(500) | sim | Descrição do produto |
| `eans` | VARCHAR(500) | sim | EANs do produto, concatenados por vírgula |
| `leaflet_id` | VARCHAR(50) | sim | ID do encarte |
| `number_of_pages` | INTEGER | sim | Nº de páginas do encarte |
| `leaflet_name` | VARCHAR(255) | sim | Nome do encarte |
| `leaflet_type` | VARCHAR(100) | sim | Tipo do encarte |
| `delivery_channel` | VARCHAR(100) | sim | Canal (ex: `PRINTED`) |
| `store_id` | VARCHAR(50) | sim | ID da loja concorrente |
| `store_name` | VARCHAR(255) | sim | Nome da loja concorrente |
| `value` | FLOAT | sim | Preço anunciado |
| `validity_start_date` | DATE | sim | Início da vigência do preço |
| `validity_finish_date` | DATE | sim | Fim da vigência do preço |
| `dynamic` | VARCHAR(100) | sim | Tipo de oferta (ex: `OFERTA_DE_POR`) |
| `minimum_quantity` | INTEGER | sim | Quantidade mínima para o preço valer |
| `details` | TEXT | sim | Detalhes adicionais |
| `page` | INTEGER | sim | Página do encarte onde aparece |
| `city_name` | VARCHAR(255) | sim | Cidade |
| `city_id` | VARCHAR(50) | sim | ID da cidade |
| `network_id` | VARCHAR(50) | sim | ID da rede de lojas |
| `network_name` | VARCHAR(255) | sim | Nome da rede |
| `brand_id` | VARCHAR(50) | sim | ID da marca do produto |
| `brand_name` | VARCHAR(255) | sim | Nome da marca |
| `identifier` | VARCHAR(100) | sim, único | Chave de deduplicação entre chunks (`price_id + store_id`) |
| `store_cnpj` | VARCHAR(20) | sim | CNPJ da loja concorrente |
| `created_at` | TIMESTAMP | não | Quando a linha foi gravada |

Consumo pelo BI normalmente não é direto nessa tabela — é via `fetch_infomarket_tratado()`
(exposta em `GET /api/v1/infomarket`), que remove preços "padrão" e deduplica por rede.

## `ativmob_estoque`

Eventos de estoque/vencimento da ATIVMOB (promotores em campo). Fila com ACK — nunca é
limpa, só recebe inserts novos; duplicata (mesmo `event_id`) é ignorada silenciosamente.

| Coluna | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | não | PK autoincrement |
| `event_id` | VARCHAR(50) | não, único | ID do evento na ATIVMOB — chave de deduplicação |
| `store_cnpj` | VARCHAR(20) | não | CNPJ (sem sufixo `_interior`, normalizado no load) |
| `event_code` | VARCHAR(50) | não | `estoque` (capital) ou `estoque_int` (interior) |
| `event_title` | VARCHAR(255) | sim | Título do evento |
| `event_dth` | TIMESTAMP | não | Data/hora do evento |
| `order_number` | VARCHAR(100) | sim | Número do pedido |
| `invoice_number` | VARCHAR(100) | sim | Número da nota fiscal |
| `codigo_orcamento` | VARCHAR(100) | sim | Código do orçamento |
| `agent_code` | VARCHAR(50) | sim | Código do agente/promotor |
| `agent_name` | VARCHAR(255) | sim | Nome do agente |
| `lat` / `lng` | VARCHAR(50) | sim | Coordenadas do evento |
| `codigo_roteiro` | VARCHAR(100) | sim | Código do roteiro de entrega |
| `link_rastreamento` | VARCHAR(500) | sim | Link de rastreamento |
| `razao_social_dest` | VARCHAR(500) | sim | Razão social do destino |
| `nome_fantasia_dest` | VARCHAR(500) | sim | Nome fantasia do destino |
| `codigo_destino` | VARCHAR(50) | sim | Código do destino |
| `produto_nome` | VARCHAR(500) | sim | Nome do produto (extraído do `form[]` dinâmico) |
| `produto_codigo` | VARCHAR(50) | sim | Código do produto (extraído do `form[]`) |
| `quantidade` | INTEGER | sim | Quantidade (extraída do `form[]`) |
| `data_validade` | DATE | sim | Validade do produto (extraída do `form[]`) |
| `em_ruptura` | VARCHAR(10) | sim | `"SIM"`/`"NÃO"` (extraído do `form[]`) |
| `form_json` | TEXT | sim | JSON bruto do `form[]` completo — rede de segurança para campos não mapeados |
| `created_at` | TIMESTAMP | não | Quando a linha foi gravada |

## `ativmob_agendamentos`

Agendamentos recorrentes de visitas de agentes de campo (grade semanal fixa, não um log de
eventos). Substituída por `origem` a cada carga (`DELETE WHERE origem = :origem` + insert) —
hoje só existe a origem `capital`.

| Coluna | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | não | PK autoincrement |
| `origem` | VARCHAR(20) | não | `capital` ou `interior` (interior ainda não habilitado) — chave de escopo do replace |
| `store_cnpj` | VARCHAR(20) | sim | CNPJ consultado |
| `tipo_evento` | VARCHAR(10) | sim | Código numérico do tipo de evento vindo da API |
| `codigo_local` | VARCHAR(50) | sim | Código da loja/local visitado (API às vezes manda `NULL`) |
| `nome_agente` | VARCHAR(255) | sim | Nome do agente/promotor |
| `login` | VARCHAR(100) | sim | Login do agente no sistema ATIVMOB |
| `codigo_agente` | VARCHAR(50) | sim | Código do agente |
| `dt_referencia` | DATE | sim | Data de referência do agendamento |
| `hora_referencia` | TIME | sim | Horário de referência |
| `dom`, `seg`, `ter`, `qua`, `qui`, `sex`, `sab` | BOOLEAN | não (default `false`) | Flags de recorrência por dia da semana — `true` = agente tem essa atividade nesse dia |
| `titulo_tipo_atividade` | VARCHAR(255) | sim | Título bruto da atividade (ex: `"VISITA (PROMOTOR)"`, `"INTERVALO PARA ALMOCO"`, `"QUILOMETRAGEM (INICIO)"`), já sem espaço à direita |
| `categoria_atividade` | VARCHAR(50) | não (default `"outro"`) | Categoria derivada por prefixo do título: `visita` / `intervalo` / `quilometragem` / `outro` |
| `raw_json` | TEXT | sim | JSON bruto do registro original |
| `created_at` | TIMESTAMP | não | Quando a linha foi gravada |

## `ativmob_km`

Eventos de "conclusão de roteiro" (distância percorrida). Mesmo padrão de fila+ACK de
`ativmob_estoque`, mas sem `form[]` — os campos já vêm planos no evento.

| Coluna | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | não | PK autoincrement |
| `event_id` | VARCHAR(50) | não, único | ID do evento na ATIVMOB — chave de deduplicação |
| `store_cnpj` | VARCHAR(20) | sim | CNPJ (normalizado, sem sufixo `_interior`) |
| `event_code` | VARCHAR(50) | sim | Sempre `conclusao_roteiro` |
| `event_title` | VARCHAR(255) | sim | Título do evento |
| `event_dth` | TIMESTAMP | sim | Data/hora do evento |
| `agent_code` | VARCHAR(50) | sim | Código do agente |
| `agent_name` | VARCHAR(255) | sim | Nome do agente |
| `codigo_roteiro` | VARCHAR(100) | sim | Código do roteiro |
| `codigo_orcamento` | VARCHAR(100) | sim | Código do orçamento |
| `dist_estim` | FLOAT | sim | Distância estimada percorrida (Km) |
| `tempo_estim` | VARCHAR(50) | sim | Tempo estimado (formato bruto da API, não parseado) |
| `raw_json` | TEXT | sim | JSON bruto do evento completo |
| `created_at` | TIMESTAMP | não | Quando a linha foi gravada |

---

## Endpoints da API que expõem essas tabelas

| Endpoint | Tabela(s) | Observação |
|---|---|---|
| `GET /api/v1/vendas` | `vendas` | `?limit=&offset=&days=` |
| `GET /api/v1/vendas/completo` | `vendas` | Sem paginação |
| `GET /api/v1/vendas/stream` | `vendas` | NDJSON |
| `GET /api/v1/estoque` | `estoque` | `?limit=` (default 5000) |
| `GET /api/v1/giro-estoque` | `vendas` + `estoque` | Giro/DDE últimos 30 dias (ValeMilk) |
| `GET /api/v1/vendas/valefish` | `vendas_valefish` | |
| `GET /api/v1/estoque/valefish` | `estoque_valefish` | |
| `GET /api/v1/infomarket` | `infomarket` | Tratado (sem preço padrão, deduplicado) |
| `GET /api/v1/ativmob/agendamentos` | `ativmob_agendamentos` | Snapshot bruto |
| `GET /api/v1/ativmob/agendamentos/por-dia` | `ativmob_agendamentos` | Despivotado (agente × dia × loja) |
| `GET /api/v1/ativmob/km` | `ativmob_km` | |

Todas exigem `Authorization: Bearer <API_AUTH_TOKEN>`, exceto `/health`.
