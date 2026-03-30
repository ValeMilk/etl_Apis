"""
ETL Worker - Processo separado para extração, transformação e carga.

Executa jobs de ETL em schedule independente da API FastAPI.
Permite observabilidade isolada e tolerância a falhas.
"""
import logging
import signal
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from api_cometa import CometaClient
from App.core.config import settings
from App.core.database import DatabaseClient
from App.etl.etl_service import ETLService

# Carrega variáveis de ambiente
load_dotenv()

# Configura logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
)
logger = logging.getLogger("ETL_Worker")

# Shutdown graceful
shutdown_requested = False


def signal_handler(signum, frame):
    """Handler para SIGTERM/SIGINT (graceful shutdown)."""
    global shutdown_requested
    logger.warning("Shutdown signal received (signal=%s). Finishing current job...", signum)
    shutdown_requested = True


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def run_etl_job():
    """Executa job completo de ETL (vendas + estoque)."""
    if shutdown_requested:
        logger.info("Shutdown requested, skipping job execution")
        return

    job_start = datetime.now()
    logger.info("=" * 80)
    logger.info("ETL Job Started at %s", job_start.isoformat())
    logger.info("=" * 80)

    try:
        # Inicializa clientes
        cometa_client = CometaClient(
            base_url=settings.api_base_url,
            email=settings.api_email,
            password=settings.api_password.get_secret_value(),
            timeout=settings.request_timeout,
            verify_ssl=settings.verify_ssl,
            token_refresh_hours=settings.token_refresh_hours,
        )
        logger.info("CometaClient initialized")

        db_client = DatabaseClient(
            db_url=settings.db_url, 
            echo=settings.database_echo
        )
        logger.info("DatabaseClient initialized")

        etl_service = ETLService(cometa_client, db_client)
        logger.info("ETLService initialized")

        # Processa Vendas
        logger.info("Starting Vendas processing...")
        etl_service.processar_vendas()
        logger.info("Vendas processing completed")

        # Processa Estoque
        logger.info("Starting Estoque processing...")
        etl_service.processar_estoque()
        logger.info("Estoque processing completed")

        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.info("=" * 80)
        logger.info("ETL Job Completed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)
        logger.info("=" * 80)

    except Exception:
        logger.exception("ETL Job failed with exception")
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.error("ETL Job Failed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)


def main():
    """Entry point do ETL Worker."""
    logger.info("ETL Worker Starting...")
    logger.info("Configuration loaded: interval=%d minutes", settings.etl_interval_minutes)
    logger.info("Environment: %s", settings.app_environment)

    # Configura scheduler com BlockingScheduler (para processos standalone)
    scheduler = BlockingScheduler()

    # Agenda job a cada X minutos
    scheduler.add_job(
        run_etl_job,
        "interval",
        minutes=settings.etl_interval_minutes,
        id="etl_job",
        name="ETL Job (Vendas + Estoque)",
        next_run_time=datetime.now(),  # Executa imediatamente no startup
    )

    logger.info("Scheduler configured with %d job(s)", len(scheduler.get_jobs()))
    logger.info("Next ETL run scheduled for: %s", scheduler.get_jobs()[0].next_run_time)

    try:
        logger.info("Starting scheduler (blocking mode)...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Scheduler interrupted, shutting down...")
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped gracefully")
        sys.exit(0)


if __name__ == "__main__":
    main()
