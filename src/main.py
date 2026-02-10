import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI

from api_cometa import CometaClient
from App.api.routes import create_router
from App.core.database import DatabaseClient
from App.etl.etl_service import ETLService


def _configure_logging() -> None:
	log_level = os.getenv("LOG_LEVEL", "INFO").upper()
	logging.basicConfig(
		level=log_level,
		format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
	)


load_dotenv()
_configure_logging()

logger = logging.getLogger("Main")

db_url = os.getenv("DB_URL", "")
if not db_url:
	logger.warning("DB_URL is not set")

cometa_client = CometaClient(
	base_url=os.getenv("API_BASE_URL", ""),
	email=os.getenv("API_EMAIL", ""),
	password=os.getenv("API_PASSWORD", ""),
	timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
	verify_ssl=os.getenv("VERIFY_SSL", "false").lower() == "true",
)
db_client = DatabaseClient(db_url=db_url)
etl_service = ETLService(cometa_client, db_client)

app = FastAPI(title="BI_COMETA", version="1.0.0")
app.include_router(create_router(db_client))

scheduler = BackgroundScheduler()


@app.on_event("startup")
def on_startup() -> None:
	logger.info("Starting scheduler")
	scheduler.add_job(etl_service.processar_estoque, "interval", hours=1, id="etl_estoque")
	scheduler.add_job(etl_service.processar_vendas, "interval", hours=1, id="etl_vendas")
	scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
	logger.info("Stopping scheduler")
	scheduler.shutdown(wait=False)
