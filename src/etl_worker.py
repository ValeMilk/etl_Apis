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
from infomarket_client import InfomarketClient
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


def run_vendas_estoque_job():
    """Executa job de Vendas + Estoque (ValeMilk + ValeFish) - 1x por dia."""
    if shutdown_requested:
        logger.info("Shutdown requested, skipping job execution")
        return

    job_start = datetime.now()
    logger.info("=" * 80)
    logger.info("VENDAS+ESTOQUE Job Started at %s", job_start.isoformat())
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
        logger.info("CometaClient [ValeMilk] initialized")

        db_client = DatabaseClient(
            db_url=settings.db_url, 
            echo=settings.database_echo
        )
        logger.info("DatabaseClient initialized")

        etl_service = ETLService(cometa_client, db_client, target="valemilk")
        logger.info("ETLService [ValeMilk] initialized")

        # Processa Vendas ValeMilk
        logger.info("Starting Vendas [ValeMilk] processing...")
        etl_service.processar_vendas()
        logger.info("Vendas [ValeMilk] processing completed")

        # Processa Estoque ValeMilk
        logger.info("Starting Estoque [ValeMilk] processing...")
        etl_service.processar_estoque()
        logger.info("Estoque [ValeMilk] processing completed")

        # ── ValeFish ──
        if settings.valefish_api_email:
            cometa_client_valefish = CometaClient(
                base_url=settings.api_base_url,
                email=settings.valefish_api_email,
                password=settings.valefish_api_password.get_secret_value(),
                timeout=settings.request_timeout,
                verify_ssl=settings.verify_ssl,
                token_refresh_hours=settings.token_refresh_hours,
            )
            logger.info("CometaClient [ValeFish] initialized")

            etl_service_valefish = ETLService(cometa_client_valefish, db_client, target="valefish")
            logger.info("ETLService [ValeFish] initialized")

            logger.info("Starting Vendas [ValeFish] processing...")
            etl_service_valefish.processar_vendas()
            logger.info("Vendas [ValeFish] processing completed")

            logger.info("Starting Estoque [ValeFish] processing...")
            etl_service_valefish.processar_estoque()
            logger.info("Estoque [ValeFish] processing completed")
        else:
            logger.info("ValeFish credentials not configured, skipping")

        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.info("=" * 80)
        logger.info("VENDAS+ESTOQUE Job Completed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)
        logger.info("=" * 80)

    except Exception:
        logger.exception("VENDAS+ESTOQUE Job failed with exception")
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.error("VENDAS+ESTOQUE Job Failed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)


def run_infomarket_job():
    """Executa job de InfoMarket (encartes/preços) - 3x por dia."""
    if shutdown_requested:
        logger.info("Shutdown requested, skipping job execution")
        return

    job_start = datetime.now()
    logger.info("=" * 80)
    logger.info("INFOMARKET Job Started at %s", job_start.isoformat())
    logger.info("=" * 80)

    try:
        db_client = DatabaseClient(
            db_url=settings.db_url, 
            echo=settings.database_echo
        )

        # ── InfoMarket (encartes/preços) ──
        if settings.infomarket_email:
            from datetime import timedelta
            try:
                infomarket_client = InfomarketClient(
                    email=settings.infomarket_email,
                    password=settings.infomarket_password.get_secret_value(),
                    timeout=settings.request_timeout,
                )
                logger.info("InfomarketClient initialized")

                hoje = datetime.now().date()
                
                # Tenta puxar incremental: última data sincronizada + 1 dia
                last_sync_date = db_client.get_last_infomarket_date()
                if last_sync_date:
                    # Incremental: puxar desde o dia após última sincronização
                    # ETL roda 3x ao dia (a cada 8h), capturando atualizações frequentes
                    start_date = last_sync_date
                    logger.info("Incremental mode: last sync was %s, starting from %s", 
                               last_sync_date, start_date)
                else:
                    # Bootstrap mode: se tabela vazia, puxar últimos 90 dias
                    start_date = hoje - timedelta(days=settings.infomarket_lookback_days)
                    logger.info("Bootstrap mode: pulling last %d days", settings.infomarket_lookback_days)
                
                finish_date = hoje + timedelta(days=settings.infomarket_lookahead_days)

                logger.info(
                    "Starting InfoMarket processing (%s → %s)...",
                    start_date.strftime("%Y-%m-%d"), finish_date.strftime("%Y-%m-%d")
                )
                records = infomarket_client.get_prices(start_date, finish_date)
                if records:
                    deleted, inserted = db_client.replace_infomarket(records)
                    logger.info("InfoMarket finished. Deleted=%d Inserted=%d", deleted, inserted)
                else:
                    logger.warning("InfoMarket: nenhum registro retornado")
            except Exception as e:
                logger.warning("InfoMarket skipped due to error: %s", e)
        else:
            logger.info("InfoMarket credentials not configured, skipping")

        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.info("=" * 80)
        logger.info("INFOMARKET Job Completed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)
        logger.info("=" * 80)

    except Exception:
        logger.exception("INFOMARKET Job failed with exception")
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.error("INFOMARKET Job Failed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)


def main():
    """Entry point do ETL Worker."""
    logger.info("ETL Worker Starting...")
    logger.info("Configuration loaded")
    logger.info("Environment: %s", settings.app_environment if hasattr(settings, 'app_environment') else 'production')

    # Configura scheduler com BlockingScheduler (para processos standalone)
    scheduler = BlockingScheduler()

    # JOB 1: Vendas + Estoque (ValeMilk + ValeFish) - 1x por dia às 02:00
    scheduler.add_job(
        run_vendas_estoque_job,
        "cron",
        hour=2,
        minute=0,
        id="vendas_estoque_job",
        name="Vendas + Estoque (ValeMilk + ValeFish) - Diário",
    )

    # JOB 2: InfoMarket (encartes/preços) - 3x por dia (08h, 16h, 00h)
    scheduler.add_job(
        run_infomarket_job,
        "cron",
        hour="0,8,16",
        minute=0,
        id="infomarket_job",
        name="InfoMarket - 3x ao dia",
    )

    logger.info("Scheduler configured with %d job(s):", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logger.info("  - %s", job.name)

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
