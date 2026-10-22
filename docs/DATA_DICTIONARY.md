# Dicionário de Dados — PostgreSQL (bi_cometa)

> Gerado a partir do schema real em `src/App/core/database.py` (fonte da verdade — as
> tabelas são criadas via `MetaData.create_all()`, sem Alembic/migrations). Se o schema
> mudar, atualize este arquivo junto.
>
> Nenhuma tabela tem foreign key formal entre si — o banco é deliberadamente flat (sem
> JSONB), e os relacionamentos (ex: `vendas.cod_interno` ↔ `estoque.codigo_produto`) são
> lógicos, resolvidos nas consultas, não por constraint.

## Visão geral das 8 tabelas e 1 view

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
| `infomarket_tratado` | View sobre `infomarket` (mesmo tratamento do BI) | Calculada a cada consulta, sem carga própria | — (`sql/infomarket_tratado.sql`) |

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

**Não use esta tabela para análise de encartes/preços** — ela tem uma linha por loja e inclui o preço
"padrão", então contagens e médias saem cerca de 10x infladas. O BI consome o dado tratado, via
`fetch_infomarket_tratado()` (exposta em `GET /api/v1/infomarket`); no banco, o equivalente é a view
`infomarket_tratado` (próxima seção). Use `infomarket` crua só para olhar loja a loja.

## `infomarket_tratado` (view)

**É a fonte certa para encartes e preços de concorrentes.** Mesmas colunas e tipos de `infomarket`,
exceto `store_id`, `store_name` e `store_cnpj` (as lojas da mesma rede viram uma linha só). Definida em
`sql/infomarket_tratado.sql`, espelho de `fetch_infomarket_tratado()`; não tem carga própria.

Regras do tratamento, nesta ordem, dentro de cada grupo
`(network_id, brand_id, item_id, leaflet_id, validity_start_date, validity_finish_date)`:

1. **Preço padrão:** se o grupo tem mais de um `value`, as linhas com o maior valor são descartadas
   (é o preço de prateleira); sobra o preço da oferta. Grupo com um único valor fica como está.
2. **Deduplicação por rede:** uma linha por grupo + `value`, mantendo a de `created_at` mais recente.

Efeito medido (marca MARANGUAPE, encartes vigentes nos 3 meses até 22/10/2026): 7.821 linhas em
`infomarket` → 775 em `infomarket_tratado`. Na tabela inteira: 236.862 → 17.039 linhas (94 redes, 195 marcas).

Como consultar:

- `brand_name` e `network_name` são texto em MAIÚSCULAS (ex.: `MARANGUAPE`, `SUPERMERCADO GUARA`), e 18 redes
  têm acento no nome (ex.: `ATACADÃO`). O `ILIKE` **não ignora acento** (medido em 22/10/2026: `ILIKE '%atacadao%'`
  acha 0 linhas, `'%atacadão%'` acha 951) e a extensão `unaccent` não está instalada. O usuário escreve sem acento
  ou com acento diferente do cadastro, então compare sem acento nos dois lados, com o termo já em MAIÚSCULAS:
  `translate(upper(network_name), 'ÃÁÀÂÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC') LIKE '%ATACADAO%'`. Vale igual para `brand_name`.
  Antes de montar o relatório, confira qual nome existe:
  `SELECT DISTINCT network_name FROM infomarket_tratado WHERE <filtro acima>`.
- "Encartes de um período" = encartes **vigentes** nele:
  `validity_finish_date >= <início> AND validity_start_date <= <fim>`.
- `leaflet_name` identifica o encarte; uma rede pode ter vários no mesmo período. `value` é o preço
  anunciado e `dynamic` o tipo de oferta (ex.: `OFERTA_DE_POR`).
- Cobertura: `validity_start_date` vai de 03/03/2026 (primeira carga) até encartes futuros já cadastrados;
  não há dados de antes disso.

### Racional para perguntas de encartes (ex.: "histórico de encartes na rede Cometa de requeijão 400g")

Esta view é o mesmo tratamento da consulta em linguagem M do Power BI da Vale Milk, em três passos, dentro
de cada grupo `(rede, marca, item, encarte, vigência)`: (1) achar o menor e o maior `value`; (2) se são
diferentes, descartar as linhas com o maior (é o preço de prateleira que a InfoMarket repete por loja);
(3) das lojas da rede que sobraram, ficar com uma linha por preço (a mais recente). Por isso **nunca** se
soma, conta ou tira média em `infomarket`: o resultado sai ~10x inflado e com o preço padrão misturado.

Como raciocinar, nesta ordem:

1. **Separe a pergunta em cinco dimensões.** REDE (`network_name`), CATEGORIA e GRAMATURA (as duas vivem
   dentro de `description`), MARCA (`brand_name`; `VALEMILK` e `VALEFISH` são as marcas do grupo, as demais
   são concorrentes; `VALEDOURADO` NÃO é do grupo) e PERÍODO. Sem período na pergunta, use o histórico inteiro
   (desde 03/03/2026) e diga isso na resposta.
2. **Resolva a rede antes de tudo**, sem acento e em maiúsculas (ver acima), e confira com `SELECT DISTINCT
   network_name`. O `LIKE '%X%'` pode casar VÁRIAS redes: `'%ATACADAO%'` devolve `ATACADÃO`, `ATACADÃO CURIÓ
   MIX` e `LAG ATACADÃO`, que são redes diferentes. Depois do DISTINCT, filtre a escolhida com
   `network_name = '<nome exato>'`; se houver mais de uma plausível, responda pela principal e cite as outras.
   "Cometa" existe como `COMETA` (uma rede só; os nomes de loja, como "COMETA MONTESE" ou "GUARARAPES",
   aparecem só dentro de `leaflet_name`).
3. **Categoria e gramatura saem de `description`, não de EAN.** Não há coluna de categoria; `eans` é nulo em
   ~8% das linhas e não casa com `vendas` (lá o EAN é sempre nulo). O texto é padronizado em maiúsculas:
   `<CATEGORIA> [CREMOSO] <MARCA> <VARIANTE> <EMBALAGEM> <GRAMATURA>`, ex.:
   `REQUEIJÃO CREMOSO VALEMILK TRADICIONAL POTE 400G`, `IOGURTE POLPA BETÂNIA SABORES BANDEJA 540G`.
   - Categoria = primeira palavra. As que existem (22/10/2026): IOGURTE, REQUEIJÃO, BEBIDA (láctea), FILÉ
     (peixe, ValeFish), MANTEIGA, QUEIJO, DOCE (de leite), e raras (CAPPUCCINO, COALHADA, ISCAS, SHAKE,
     TILÁPIA, ACHOCOLATADO, LEITE, CREME...). Filtre sem acento e com `trim` (13 linhas começam com espaço e
     1 está grafada "BEBIBA"):
     `translate(upper(trim(description)), 'ÃÁÀÂÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC') LIKE 'REQUEIJAO%'`
     (use `'%REQUEIJ%'` só se quiser pegar também "MISTURA DE REQUEIJÃO"). "Iogurte" em sentido amplo
     inclui BEBIDA LÁCTEA fermentada e LEITE FERMENTADO: decida se entram e declare.
   - Gramatura = último token, nos formatos `400G`, `200G`, `1.15KG`, `250ML`, `1L` (ponto como decimal,
     às vezes com espaço: "400 G"). Compare sem espaços e **ancorado no fim**, senão `400G` casa `1400G`:
     `regexp_replace(upper(description), '\s', '', 'g') ~ '[^0-9.,]400G$'`.
     Exceções: queijo coalho e filés de peixe são vendidos por PESO VARIÁVEL, a descrição termina em `KG`
     sem número (~1.300 linhas) e `value` é R$/kg, então não use filtro de gramatura; algumas descrições
     têm gramatura dupla ("175/170G", "800G/850G"), ponto final ("180G.") ou lixo ("540G APAGAR"). Se o
     filtro ancorado devolver pouco, confira com `LIKE '%170G%'`.
   - Variante (TRADICIONAL, LIGHT, ZERO LACTOSE) e embalagem (POTE, COPO, VIDRO, BISNAGA) também estão no
     texto; só filtre por elas se a pergunta pedir. "Requeijão 400g" inclui tradicional e light.
4. **Monte o histórico como uma linha por oferta**, agrupando por
   `(validity_start_date, validity_finish_date, trim(leaflet_name), leaflet_type, brand_name, description,
   value, dynamic)` com `COUNT(DISTINCT leaflet_id) AS encartes`, em ordem de `validity_start_date`. O MESMO
   encarte sai com 2+ `leaflet_id` quando a rede imprime uma versão por loja/praça (ex.: "CARNES" do Cometa):
   conte `leaflet_id` distintos, nunca linhas. `leaflet_name` é o nome comercial do encarte ("EXPLOSÃO DE
   OFERTAS", "CLUBE TEM MAIS PRA VOCÊ"), não um identificador estável: o mesmo encarte aparece com e sem
   espaço final e com variantes ("CARNES", "CARNES ", "CARNES COMETA", "TEM MAIS PRA/PARA VOCÊ"), por isso
   o `trim`. `leaflet_type` é o formato: SEMANAL, FIM DE SEMANA, FRIGORIFICO (o tabloide "CARNES" de 1-2
   dias que também leva laticínios), FORNECEDOR (encarte temático/patrocinado, com nome de fabricante ou
   festival; 73% têm uma marca só, mas pode ter várias, ex.: "BATAVO" no Cometa tem 7 marcas), ABASTECEDOR,
   DIARIO, INAUGURAÇÃO, HORTIFRUTI. Duração média: ~3 dias por encarte.
5. **Leia `dynamic` antes de comparar preço.** `OFERTA_DE_POR` é o preço de oferta aberto a todos;
   `PROGRAMA_FIDELIDADE` é preço de clube/cartão (no Cometa, "Clube Tem Mais Pra Você"), `DESCONTO_APP`
   só no aplicativo e `DESCONTO_NO_CARTAO_PROPRIO` só no cartão da rede: não compare esses com o preço
   aberto sem dizer. `DESCONTO_NA_CAIXA_FECHADA` é preço de atacado por caixa e `COMBO` é pacote: fora da
   comparação de varejo. Em `A_PARTIR_DE_X_UNIDADES` e `LEVE_MAIS_PAGUE_MENOS`, `value` é sempre o preço
   UNITÁRIO na condição ("LEVE 8 PAGUE R$ 20.00" -> `value` 2,50); `minimum_quantity` é 1 por padrão
   (inclusive em metade das A_PARTIR_DE_X_UNIDADES) e `details` é texto livre, vazio em ~1/3 das
   LEVE_MAIS_PAGUE_MENOS: leia os dois como indicativos, não como regra.
6. **Resuma por marca** sobre o mesmo filtro: nº de encartes (`COUNT(DISTINCT leaflet_id)`), nº de períodos
   de vigência distintos, primeiro e último encarte, preço mínimo, médio e máximo, e quantos ENCARTES foram
   de clube (também `COUNT(DISTINCT leaflet_id)`; nunca misture contagem de linhas com contagem de encartes
   na mesma frase). Destaque as marcas do grupo contra os concorrentes: quem está mais presente, a que preço,
   qual a diferença para o preço da Vale Milk, e a recência (último encarte e preço mais recente de cada
   marca). Quando categoria+gramatura reúne SKUs de segmentos diferentes (iogurte 170g: natural, líquido,
   whey, de R$ 2,99 a 7,99), quebre também por `description` antes de comparar preço entre marcas; média por
   marca ali engana.
7. **Resultado vazio é resposta, não erro.** Se o filtro devolver zero linhas, diga isso e mostre (a) o
   histórico fora do período e (b) a gramatura que a rede de fato anuncia na categoria (ex.: o Atacadão
   anuncia manteiga quase só em 500g), em vez de afrouxar o filtro em silêncio.
8. **Na resposta, declare sempre:** a rede exata encontrada, o filtro de `description` usado, o período
   coberto, que "encarte" = `leaflet_id` distinto, que os preços são os ANUNCIADOS depois do tratamento (sem
   preço padrão), e que a base começa em 03/03/2026. `created_at` é a hora da recarga (3x/dia), nunca a
   data do encarte: datas vêm só de `validity_*`.

Modelo testado em 22/10/2026 (histórico):

```sql
SELECT validity_start_date AS inicio, validity_finish_date AS fim, trim(leaflet_name) AS encarte,
       leaflet_type AS tipo, brand_name AS marca, description AS produto, value AS preco,
       dynamic AS oferta, COUNT(DISTINCT leaflet_id) AS encartes
FROM infomarket_tratado
WHERE network_name = 'COMETA'
  AND translate(upper(trim(description)), 'ÃÁÀÂÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC') LIKE 'REQUEIJAO%'
  AND regexp_replace(upper(description), '\s', '', 'g') ~ '[^0-9.,]400G$'
  -- AND validity_finish_date >= '<início>' AND validity_start_date <= '<fim>'
GROUP BY 1,2,3,4,5,6,7,8
ORDER BY 1 DESC, 5;
```

Resumo por marca (mesmo `WHERE`):

```sql
SELECT brand_name AS marca, COUNT(DISTINCT leaflet_id) AS encartes,
       COUNT(DISTINCT (validity_start_date, validity_finish_date)) AS periodos,
       MIN(validity_start_date) AS primeiro, MAX(validity_finish_date) AS ultimo,
       ROUND(MIN(value)::numeric, 2) AS preco_min, ROUND(AVG(value)::numeric, 2) AS preco_medio,
       ROUND(MAX(value)::numeric, 2) AS preco_max,
       COUNT(DISTINCT leaflet_id) FILTER (WHERE dynamic = 'PROGRAMA_FIDELIDADE') AS encartes_clube
FROM infomarket_tratado
WHERE <mesmo filtro>
GROUP BY 1 ORDER BY 2 DESC;
```

No Cometa, requeijão 400g (histórico até 22/10/2026) devolve 8 marcas; SABOR & VIDA lidera em encartes
(43), VALEMILK vem em seguida (31, preço de R$ 10,99 a 11,99, 8 encartes de clube) e MARANGUAPE (25). É
este o formato de resposta esperado: tabela do histórico + leitura por marca com a Vale Milk em destaque.

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
