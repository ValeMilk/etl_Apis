import logging
from fastapi import APIRouter

from App.core.database import DatabaseClient


def create_router(db_client: DatabaseClient) -> APIRouter:
    router = APIRouter()
    logger = logging.getLogger("Routes")

    @router.get("/api/v1/vendas")
    def listar_vendas():
        logger.info("GET /api/v1/vendas")
        return db_client.fetch_vendas()

    @router.get("/api/v1/estoque")
    def listar_estoque():
        logger.info("GET /api/v1/estoque")
        return db_client.fetch_estoque()

    return router
