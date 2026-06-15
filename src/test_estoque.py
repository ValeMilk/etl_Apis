#!/usr/bin/env python
"""Teste rápido de sincronização de estoque"""
import logging
from datetime import datetime
from api_cometa import CometaClient
from App.core.config import settings
from App.core.database import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_estoque")

logger.info("Inicializando cliente...")
cometa = CometaClient(
    base_url=settings.api_base_url,
    email=settings.api_email,
    password=settings.api_password.get_secret_value(),
    timeout=60,
    verify_ssl=settings.verify_ssl,
)

logger.info("Puxando estoque da API...")
estoque = cometa.get_estoque()
logger.info(f"✅ Estoque: {len(estoque)} registros")

if estoque:
    logger.info(f"Amostra: {estoque[0]}")
    
    # Conecta ao banco
    db = DatabaseClient(db_url=settings.db_url)
    logger.info("Inserindo no banco...")
    deleted, inserted = db.replace_estoque(estoque)
    logger.info(f"✅ Deletados: {deleted}, Inseridos: {inserted}")
else:
    logger.warning("❌ Nenhum dado retornado!")
