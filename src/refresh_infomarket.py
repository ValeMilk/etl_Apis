#!/usr/bin/env python3
"""
Script para refresh completo dos dados InfoMarket.
Deleta todos os registros e repuxa últimos 200 dias.
Usa chunking por mês para evitar timeout da API.
"""
import sys
import logging
import time
from datetime import datetime, timedelta
from typing import List

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


def get_date_chunks(start_date, end_date, chunk_days=30):
    """
    Divide período em chunks menores para evitar timeout.
    Retorna lista de tuplas (start, end).
    """
    chunks = []
    current = start_date
    
    while current < end_date:
        chunk_end = min(current + timedelta(days=chunk_days), end_date)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    
    return chunks


def fetch_with_retry(infomarket_client, start_date, finish_date, max_retries=3):
    """
    Tenta buscar dados com retry em caso de erro 502/timeout.
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Tentativa {attempt}/{max_retries} para período {start_date} → {finish_date}")
            records = infomarket_client.get_prices(start_date, finish_date)
            logger.info(f"✅ Sucesso! {len(records)} registros")
            return records
        except Exception as e:
            if "502" in str(e) or "timeout" in str(e).lower():
                if attempt < max_retries:
                    wait_time = 10 * attempt  # Backoff: 10s, 20s, 30s
                    logger.warning(f"⚠️ Erro {e.__class__.__name__}, aguardando {wait_time}s antes de retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Falhou após {max_retries} tentativas")
                    raise
            else:
                # Erro diferente de 502/timeout, não faz retry
                raise
    
    return []


def main():
    """Limpa e repuxa dados InfoMarket dos últimos 200 dias em chunks."""
    
    logger.info("=" * 80)
    logger.info("REFRESH INFOMARKET - Deletar tudo e repuxar últimos 200 dias")
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
        
        # Step 2: Calcular chunks de 30 dias
        logger.info("")
        logger.info("Step 2: Calculando chunks para evitar timeout da API...")
        hoje = datetime.now().date()
        start_date = hoje - timedelta(days=200)
        finish_date = hoje + timedelta(days=60)  # Inclui encartes futuros
        
        chunks = get_date_chunks(start_date, finish_date, chunk_days=30)
        logger.info(f"📅 Período total: {start_date} → {finish_date} ({(finish_date - start_date).days} dias)")
        logger.info(f"📦 Dividido em {len(chunks)} chunks de ~30 dias cada")
        
        # Step 3: Processar cada chunk com retry
        total_inserted = 0
        for idx, (chunk_start, chunk_end) in enumerate(chunks, 1):
            logger.info("")
            logger.info(f"{'='*60}")
            logger.info(f"📦 CHUNK {idx}/{len(chunks)}: {chunk_start} → {chunk_end}")
            logger.info(f"{'='*60}")
            
            try:
                # Buscar dados com retry
                records = fetch_with_retry(infomarket_client, chunk_start, chunk_end, max_retries=3)
                
                if records:
                    # Inserir no banco
                    logger.info(f"💾 Inserindo {len(records)} registros no banco...")
                    deleted, inserted = db_client.replace_infomarket(records)
                    total_inserted += inserted
                    logger.info(f"✅ Chunk {idx}/{len(chunks)} completo: +{inserted} registros (total: {total_inserted})")
                else:
                    logger.warning(f"⚠️ Chunk {idx}/{len(chunks)} retornou 0 registros")
                
                # Pausa entre chunks para não sobrecarregar API
                if idx < len(chunks):
                    logger.info("⏸️ Aguardando 5s antes do próximo chunk...")
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"❌ Erro no chunk {idx}/{len(chunks)}: {e}")
                logger.error(f"⚠️ Dados até aqui foram salvos ({total_inserted} registros)")
                logger.error(f"💡 Você pode reexecutar o script - ele vai sobrescrever com dados completos")
                return 1
        
        # Resumo final
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ REFRESH INFOMARKET COMPLETO")
        logger.info(f"📊 Total inserido: {total_inserted} registros")
        logger.info(f"📅 Período: {start_date} → {finish_date}")
        logger.info(f"📦 Chunks processados: {len(chunks)}")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error("❌ Erro durante refresh do InfoMarket", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
