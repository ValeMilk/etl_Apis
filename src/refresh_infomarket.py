#!/usr/bin/env python3
"""
Script para refresh completo dos dados InfoMarket.
Deleta todos os registros e repuxa últimos 120 dias.
"""
import sys
import logging
from datetime import datetime, timedelta

sys.path.insert(0, '/app')

from sqlalchemy import text, delete
from infomarket_client import InfomarketClient
from App.core.config import settings
from App.core.database import DatabaseClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger("RefreshInfoMarket")


def main():
    """Limpa e repuxa dados InfoMarket dos últimos 120 dias."""
    
    logger.info("=" * 80)
    logger.info("REFRESH INFOMARKET - Deletar tudo e repuxar últimos 120 dias")
    logger.info("=" * 80)
    
    try:
        # Inicializa clientes
        db_client = DatabaseClient(
            db_url=settings.db_url,
            echo=False
        )
        logger.info("✅ DatabaseClient inicializado")
        
        infomarket_client = InfomarketClient(
            email=settings.infomarket_email,
            password=settings.infomarket_password.get_secret_value(),
            timeout=settings.request_timeout,
        )
        logger.info("✅ InfomarketClient inicializado")
        
        # Step 1: TRUNCAR tabela (mais rápido que DELETE)
        logger.info("")
        logger.info("Step 1: TRUNCANDO tabela infomarket...")
        with db_client.get_session() as session:
            session.execute(text("TRUNCATE TABLE infomarket RESTART IDENTITY CASCADE"))
            deleted_count = session.execute(text("SELECT COUNT(*) FROM infomarket")).scalar()
        logger.info(f"✅ Tabela truncada (registros restantes: {deleted_count})")
        
        # Step 2: Puxar últimos 120 dias
        logger.info("")
        logger.info("Step 2: Puxando últimos 200 dias da API InfoMarket...")
        hoje = datetime.now().date()
        start_date = hoje - timedelta(days=200)
        finish_date = hoje + timedelta(days=60)  # Inclui encartes futuros
        
        logger.info(f"📅 Período: {start_date} → {finish_date}")
        logger.info(f"📊 Total de dias: {(finish_date - start_date).days}")
        
        records = infomarket_client.get_prices(start_date, finish_date)
        logger.info(f"✅ API retornou {len(records)} registros")
        
        # Step 3: Inserir no banco (usando replace_infomarket que já tem a lógica de preparação)
        if records:
            logger.info("")
            logger.info("Step 3: Inserindo registros no banco...")
            # Como truncamos antes, replace_infomarket vai só inserir
            deleted, inserted = db_client.replace_infomarket(records)
            logger.info(f"✅ Inseridos {inserted} registros")
        else:
            logger.warning("⚠️ Nenhum registro retornado pela API!")
        
        # Resumo
        logger.info("")
        logger.info("=" * 80)
        logger.info("REFRESH INFOMARKET COMPLETO")
        logger.info(f"Inseridos: {inserted if records else 0}")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error("❌ Erro durante refresh do InfoMarket", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
