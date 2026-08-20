import logging
import json
from typing import List, Union

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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
    def listar_vendas(token: TokenDep, limit: int = 0, offset: int = 0, days: int = 0) -> List[dict]:
        """
        Retorna vendas em ordem cronológica reversa.
        Default: sem limite (retorna todos os registros).
        Use ?limit=N&offset=M para paginação (buscar N registros pulando M).
        Use ?days=N para retornar apenas últimos N dias (0 = sem filtro).
        Requer autenticação via Bearer token.
        
        Colunas: data, loja_id, nome_loja, cnpj_loja, ean, cod_interno,
                 plu, produto, qtd, venda, custo, created_at
        
        Query params:
        - limit: número máximo de registros (0 = sem limite, default)
        - offset: pular N registros para paginação (0 = início, default)
        - days: filtrar últimos N dias (0 = sem filtro, default)
        """
        effective_limit = limit if limit > 0 else None
        logger.info("GET /api/v1/vendas limit=%s offset=%s days=%s", effective_limit or "ALL", offset, days or "ALL")
        return db_client.fetch_vendas(limit=effective_limit, offset=offset, days=days if days > 0 else None)

    @router.get("/api/v1/vendas/completo")
    def listar_vendas_completo(token: TokenDep) -> List[dict]:
        """
        Retorna TODOS os registros de vendas em uma única requisição.
        Otimizado para Power BI Desktop/Service (sem paginação).
        Requer autenticação via Bearer token.
        
        ⚠️ AVISO: Retorna todos os registros (~543k) - pode demorar 4-5 minutos.
        Use este endpoint para importar dados completos no Power BI.
        
        Colunas: data, loja_id, nome_loja, cnpj_loja, ean, cod_interno,
                 plu, produto, qtd, venda, custo, created_at
        """
        logger.info("GET /api/v1/vendas/completo - Buscando todos os registros")
        return db_client.fetch_vendas()

    @router.get("/api/v1/vendas/stream")
    def listar_vendas_stream(token: TokenDep):
        """
        Retorna TODOS os registros de vendas em formato NDJSON (streaming).
        MAS RÁPIDO que /completo - ideal para Power BI.
        Cada linha é um registro JSON, separado por newline.
        
        ⚠️ AVISO: Retorna todos os registros (~543k) - pode demorar 2-3 minutos.
        Use este endpoint para importar dados completos no Power BI.
        """
        logger.info("GET /api/v1/vendas/stream - Iniciando stream")
        
        def generate():
            """Generator que retorna registros um por um em formato NDJSON"""
            registros = db_client.fetch_vendas()
            for registro in registros:
                yield json.dumps(registro) + "\n"
        
        return StreamingResponse(generate(), media_type="application/x-ndjson")

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

    # ── InfoMarket Endpoints ──

    @router.get("/api/v1/infomarket")
    def listar_infomarket(token: TokenDep, limit: int = 0, debug: bool = False) -> Union[List[dict], dict]:
        """
        Retorna encartes/preços InfoMarket tratados para Power BI.
        
        Aplicação de regras:
        - Remove preços "padrão" (maior preço quando há variação de preço)
        - Deduplica por network mantendo o registro mais recente
        
        Requer autenticação via Bearer token.
        
        Query params:
        - limit: número máximo de registros (0 = sem limite, default)
        - debug: Se True, retorna contagem em vez dos dados

        Colunas: id, price_id, item_id, description, eans, leaflet_id,
                 number_of_pages, leaflet_name, leaflet_type, delivery_channel,
                 network_id, network_name, value, validity_start_date,
                 validity_finish_date, dynamic, minimum_quantity, details,
                 page, city_name, city_id, brand_id, brand_name, identifier, created_at
        """
        if debug:
            # Modo debug
            from sqlalchemy import text
            query = text("SELECT COUNT(*) FROM public.infomarket")
            with db_client.engine.connect() as conn:
                total_raw = conn.execute(query).scalar()
            
            tratado = db_client.fetch_infomarket_tratado()
            logger.info("DEBUG: raw=%d, fetched=%d", total_raw, len(tratado))
            return {
                "debug": True,
                "total_raw_infomarket": total_raw,
                "registros_fetched": len(tratado),
                "expected_tratado": 7863
            }
        
        # Modo normal
        data = db_client.fetch_infomarket_tratado()
        effective_limit = limit if limit > 0 else None
        logger.info("GET /api/v1/infomarket limit=%s returned %d records", effective_limit or "ALL", len(data) if effective_limit is None else min(effective_limit, len(data)))
        
        if effective_limit:
            return data[:effective_limit]
        return data

    return router
