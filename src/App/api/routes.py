import logging
from typing import List

from fastapi import APIRouter

from App.api.dependencies import TokenDep
from App.core.database import DatabaseClient


def create_router(db_client: DatabaseClient) -> APIRouter:
    """
    Cria router com endpoints de dados.
    Rotas /api/v1/* são protegidas com HTTPBearer authentication.
    Retorna JSON completo sem paginação para consumo direto de BI.
    """
    router = APIRouter()
    logger = logging.getLogger("Routes")

    @router.get("/api/v1/vendas")
    def listar_vendas(token: TokenDep, limit: int = 0) -> List[dict]:
        """
        Retorna vendas em ordem cronológica reversa.
        Default: sem limite (retorna todos os registros).
        Use ?limit=N para limitar o número de registros retornados.
        Requer autenticação via Bearer token.
        
        Colunas: data, loja_id, nome_loja, cnpj_loja, ean, cod_interno,
                 plu, produto, qtd, venda, custo, created_at
        
        Query params:
        - limit: número máximo de registros (0 = sem limite, default)
        """
        effective_limit = limit if limit > 0 else None
        logger.info("GET /api/v1/vendas limit=%s", effective_limit or "ALL")
        return db_client.fetch_vendas(limit=effective_limit)

    @router.get("/api/v1/estoque")
    def listar_estoque(token: TokenDep, limit: int = 5000) -> List[dict]:
        """
        Retorna snapshot atual de estoque com limite de registros.
        Default: 5000 registros (otimizado para Power BI).
        Requer autenticação via Bearer token.
        
        Colunas: snapshot_ts, loja_id, codigo_produto, descricao_produto,
                 ean, estq_loja, estq_avaria
        
        Query params:
        - limit: número máximo de registros (default 5000)
        """
        logger.info("GET /api/v1/estoque?limit=%d", limit)
        return db_client.fetch_estoque()[:limit]

    # ── ValeFish Endpoints ──

    @router.get("/api/v1/vendas/valefish")
    def listar_vendas_valefish(token: TokenDep) -> List[dict]:
        """
        Retorna todas as vendas ValeFish em ordem cronológica reversa.
        Requer autenticação via Bearer token.
        """
        logger.info("GET /api/v1/vendas/valefish")
        return db_client.fetch_vendas_valefish()

    @router.get("/api/v1/estoque/valefish")
    def listar_estoque_valefish(token: TokenDep) -> List[dict]:
        """
        Retorna snapshot atual de estoque ValeFish.
        Requer autenticação via Bearer token.
        """
        logger.info("GET /api/v1/estoque/valefish")
        return db_client.fetch_estoque_valefish()

    @router.get("/api/v1/infomarket")
    def listar_infomarket(token: TokenDep) -> List[dict]:
        """
        Retorna encartes/preços InfoMarket tratados para Power BI.
        
        Aplicação de regras:
        - Remove preços "padrão" (maior preço quando há variação de preço)
        - Deduplica por network mantendo o registro mais recente
        
        Requer autenticação via Bearer token.

        Colunas: id, price_id, item_id, description, eans, leaflet_id,
                 number_of_pages, leaflet_name, leaflet_type, delivery_channel,
                 network_id, network_name, value, validity_start_date,
                 validity_finish_date, dynamic, minimum_quantity, details,
                 page, city_name, city_id, brand_id, brand_name, identifier, created_at
        """
        logger.info("GET /api/v1/infomarket (tratado)")
        return db_client.fetch_infomarket_tratado()

    return router
