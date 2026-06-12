"""Debug script para verificar resposta do API para um leaflet específico."""
import logging
import json
from datetime import datetime, timedelta
from sqlalchemy import text
from App.core.config import Settings
from infomarket_client import InfomarketClient
from App.core.database import DatabaseClient

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

settings = Settings()
client = InfomarketClient(
    email=settings.infomarket_email,
    password=settings.infomarket_password.get_secret_value(),
    timeout=settings.request_timeout
)
db = DatabaseClient(db_url=settings.db_url)

# Buscar dados de 90 dias atrás (mesmo range do bootstrap)
start_date = datetime.utcnow().date() - timedelta(days=90)
finish_date = datetime.utcnow().date()

logger.info(f"Fetching InfoMarket data from {start_date} to {finish_date}...")
records = client.get_prices(start_date, finish_date)

# Procura pelo leaflet_id específico
target_leaflet = "698c825ada5af33c64f70725"
found_records = [r for r in records if r.get("leaflet_id") == target_leaflet]

if found_records:
    logger.info(f"✅ Found {len(found_records)} records with leaflet_id={target_leaflet}")
    for idx, record in enumerate(found_records):
        logger.info(f"\n=== Record {idx+1}/{len(found_records)} ===")
        logger.info(f"Full JSON:\n{json.dumps(record, indent=2, default=str)}")
        logger.info(f"store_cnpj value: {record.get('store_cnpj')} (type: {type(record.get('store_cnpj')).__name__})")
        logger.info(f"store_cnpj is None: {record.get('store_cnpj') is None}")
        logger.info(f"store_cnpj is empty string: {record.get('store_cnpj') == ''}")
else:
    logger.warning(f"❌ Leaflet {target_leaflet} NOT found in API response ({len(records)} records returned)")
    
    # Mostrar alguns registros aleatórios para comparar
    if records:
        logger.info("\nSample records from API:")
        for idx, record in enumerate(records[:3]):
            logger.info(f"Sample {idx+1}: store_cnpj={record.get('store_cnpj')} | leaflet_id={record.get('leaflet_id')}")

# Também verifica no banco de dados
logger.info(f"\n=== Checking database ===")
with db.engine.connect() as conn:
    query = text("SELECT leaflet_id, store_cnpj, store_name FROM infomarket WHERE leaflet_id = :leaflet_id LIMIT 5;")
    result = conn.execute(query, {"leaflet_id": target_leaflet})
    db_records = result.fetchall()
    if db_records:
        logger.info(f"Found in database: {len(db_records)} records")
        for record in db_records:
            logger.info(f"  DB: leaflet_id={record[0]}, store_cnpj={record[1]}, store_name={record[2]}")
    else:
        logger.warning(f"NOT found in database")
