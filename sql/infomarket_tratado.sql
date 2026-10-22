-- View com o tratamento de preços do BI: espelho de DatabaseClient.fetch_infomarket_tratado()
-- (src/App/core/database.py), que alimenta GET /api/v1/infomarket. Se a lógica mudar lá, mude aqui
-- e rode de novo (CREATE OR REPLACE).
--
-- Rodar na VPS como o dono das tabelas (bi_user), na raiz do BI_COMETA:
--   docker exec -i bi_cometa_db psql -U bi_user -d bi_cometa -v ON_ERROR_STOP=1 < sql/infomarket_tratado.sql
CREATE OR REPLACE VIEW public.infomarket_tratado AS
WITH preco_tratado AS (
    SELECT
        *,
        MIN(value) OVER (
            PARTITION BY network_id, brand_id, item_id, leaflet_id, validity_start_date, validity_finish_date
        ) AS menor_preco,
        MAX(value) OVER (
            PARTITION BY network_id, brand_id, item_id, leaflet_id, validity_start_date, validity_finish_date
        ) AS maior_preco
    FROM public.infomarket
),
sem_preco_padrao AS (
    SELECT *
    FROM preco_tratado
    WHERE NOT (menor_preco <> maior_preco AND value = maior_preco)
),
deduplicado_network AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY network_id, brand_id, item_id, leaflet_id, validity_start_date, validity_finish_date, value
            ORDER BY created_at DESC, store_id
        ) AS rn_network
    FROM sem_preco_padrao
)
SELECT
    id,
    price_id,
    item_id,
    description,
    eans,
    leaflet_id,
    number_of_pages,
    leaflet_name,
    leaflet_type,
    delivery_channel,
    network_id,
    network_name,
    value,
    validity_start_date,
    validity_finish_date,
    dynamic,
    minimum_quantity,
    details,
    page,
    city_name,
    city_id,
    created_at,
    brand_id,
    brand_name,
    identifier
FROM deduplicado_network
WHERE rn_network = 1;

-- O role do MCP (somente leitura) precisa enxergar a view.
GRANT SELECT ON public.infomarket_tratado TO bi_mcp;
