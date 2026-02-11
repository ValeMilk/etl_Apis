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
    def listar_vendas(token: TokenDep) -> List[dict]:
        """
        Retorna todas as vendas em ordem cronológica reversa (mais recentes primeiro).
        Sem paginação - retorna todas as linhas.
        Requer autenticação via Bearer token.
        
        Colunas: data, loja_id, nome_loja, cnpj_loja, ean, cod_interno,
                 plu, produto, qtd, venda, custo, created_at
        """
        logger.info("GET /api/v1/vendas")
        return db_client.fetch_vendas()

    @router.get("/api/v1/estoque")
    def listar_estoque(token: TokenDep) -> List[dict]:
        """
        Retorna snapshot atual de estoque.
        Sem paginação - retorna todos os produtos.
        Requer autenticação via Bearer token.
        
        Colunas: snapshot_ts, loja_id, codigo_produto, descricao_produto,
                 ean, estq_loja, estq_avaria
        """
        logger.info("GET /api/v1/estoque")
        return db_client.fetch_estoque()

    return router
