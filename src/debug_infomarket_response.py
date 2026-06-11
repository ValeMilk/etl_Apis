"""
Script para debugar a resposta da API InfoMarket e verificar quais campos estão disponíveis.
"""
import json
import logging
from datetime import datetime, timedelta
from infomarket_client import InfomarketClient
from App.core.config import settings

logging.basicConfig(
    level="DEBUG",
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("DebugInfoMarket")

if __name__ == "__main__":
    # Inicializa cliente
    client = InfomarketClient(
        email=settings.infomarket_email,
        password=settings.infomarket_password.get_secret_value(),
        timeout=settings.request_timeout,
    )
    logger.info("InfomarketClient initialized")

    # Puxar 1 dia recente (últimas 24h)
    hoje = datetime.now().date()
    start_date = hoje
    finish_date = hoje + timedelta(days=1)

    logger.info(f"Fetching prices from {start_date} to {finish_date}...")
    records = client.get_prices(start_date, finish_date)

    if records:
        logger.info(f"✅ Retrieved {len(records)} records")
        
        # Inspeciona o PRIMEIRO registro
        first_record = records[0]
        logger.info("=" * 80)
        logger.info("FIRST RECORD STRUCTURE:")
        logger.info("=" * 80)
        logger.info(json.dumps(first_record, indent=2, default=str))
        
        # Verifica quais campos existem
        logger.info("=" * 80)
        logger.info("AVAILABLE FIELDS:")
        logger.info("=" * 80)
        for key in sorted(first_record.keys()):
            value = first_record[key]
            logger.info(f"  {key}: {type(value).__name__} = {repr(value)[:60]}")
        
        # Checa especificamente por CNPJ
        logger.info("=" * 80)
        logger.info("SEARCHING FOR CNPJ FIELDS:")
        logger.info("=" * 80)
        cnpj_fields = [k for k in first_record.keys() if "cnpj" in k.lower()]
        if cnpj_fields:
            logger.info(f"✅ Found CNPJ fields: {cnpj_fields}")
            for field in cnpj_fields:
                logger.info(f"   {field} = {first_record[field]}")
        else:
            logger.warning("❌ NO CNPJ FIELDS FOUND")
            
            # Sugestão: campos que poderiam ser CNPJ
            logger.warning("Possible candidates (store/company related):")
            for key in first_record.keys():
                if any(term in key.lower() for term in ["store", "company", "shop", "cnpj", "cnpj", "id"]):
                    logger.warning(f"   {key} = {first_record[key]}")
    else:
        logger.warning("❌ No records returned")
