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
                
                # Sempre puxar desde 7 dias atrás até lookahead dias à frente
                # Isso garante captura de:
                # 1. Encartes que começam hoje
                # 2. Atualizações de encartes recentes
                # 3. Novos encartes futuros
                start_date = hoje - timedelta(days=7)  # Lookback de 7 dias
                finish_date = hoje + timedelta(days=settings.infomarket_lookahead_days)
                
                logger.info("InfoMarket sync mode: %s → %s (7 dias lookback + %d dias lookahead)", 
                           start_date, finish_date, settings.infomarket_lookahead_days)

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


def run_ativmob_job():
    """
    Executa job de ATIVMOB Estoque - 3x por dia.
    
    Loop até não haver mais eventos (garante que pega TODOS os eventos pendentes).
    A API retorna até 100 eventos por chamada - se retornar 100, há mais eventos.
    """
    if shutdown_requested:
        logger.info("Shutdown requested, skipping job execution")
        return

    job_start = datetime.now()
    logger.info("=" * 80)
    logger.info("ATIVMOB Job Started at %s", job_start.isoformat())
    logger.info("=" * 80)

    try:
        # Importa aqui para evitar erro se não configurado
        from ativmob_client import AtivmobClient

        # Verifica se credenciais ATIVMOB estão configuradas
        if hasattr(settings, 'ativmob_api_key') and hasattr(settings, 'ativmob_store_cnpj'):
            try:
                db_client = DatabaseClient(db_url=settings.db_url, echo=False)
                ativmob_client = AtivmobClient(
                    api_key=settings.ativmob_api_key,
                    store_cnpj=settings.ativmob_store_cnpj,
                    timeout=settings.request_timeout,
                )

                logger.info("📌 CNPJ: %s | Event: estoque", settings.ativmob_store_cnpj)

                # ── Loop para garantir que pega TODOS os eventos ──────────────
                total_events_fetched = 0
                total_events_inserted = 0
                batch_number = 0
                max_batches = 50  # Limite de segurança (50 batches * 100 = 5000 eventos max)

                logger.info("🔄 Iniciando loop de extração (até retornar < 100 eventos)...")

                while batch_number < max_batches:
                    batch_number += 1

                    # Step 1: Buscar até 100 eventos
                    logger.info("─" * 80)
                    logger.info("📦 BATCH #%d - Buscando eventos...", batch_number)
                    response = ativmob_client.get_events(event_code="estoque")
                    events = response.get("events", [])
                    max_num_events = response.get("maxNumEvents", 100)

                    if not events:
                        logger.info("✅ Nenhum evento pendente")
                        break

                    events_count = len(events)
                    total_events_fetched += events_count
                    logger.info("📥 Recebidos: %d eventos", events_count)

                    # Log de sample de event_dth para visibilidade de período
                    if events_count > 0:
                        first_event_dth = events[0].get("event_dth", "N/A")
                        last_event_dth = events[-1].get("event_dth", "N/A")
                        logger.info("📅 Período: %s → %s", first_event_dth, last_event_dth)

                    # Step 2: Inserir no banco
                    inserted_count = db_client.insert_ativmob_estoque(events)
                    total_events_inserted += inserted_count
                    logger.info("💾 Inseridos: %d eventos (ignorados %d duplicatas)", 
                               inserted_count, events_count - inserted_count)

                    # Step 3: Enviar ACK para API (marca como processados)
                    event_ids = [e.get("event_id") for e in events if e.get("event_id")]
                    if event_ids:
                        ack_success = ativmob_client.ack_events(event_ids)
                        if ack_success:
                            logger.info("✅ ACK enviado: %d eventos marcados como processados", len(event_ids))
                        else:
                            logger.warning("⚠️ Falha no ACK - eventos podem retornar")

                    logger.info("📊 Total acumulado: %d eventos recebidos | %d inseridos", 
                               total_events_fetched, total_events_inserted)

                    # Step 4: Verificar se há mais eventos
                    if events_count < max_num_events:
                        logger.info("✅ Última batch retornou %d eventos (< %d) - Sem mais eventos!", 
                                   events_count, max_num_events)
                        break

                    logger.info("🔄 Batch retornou %d eventos = continuar para próxima batch", 
                               max_num_events)

                # ── Resumo Final ──────────────────────────────────────────────
                logger.info("")
                logger.info("📦 Total de batches processadas: %d", batch_number)
                logger.info("📥 Total de eventos recebidos: %d", total_events_fetched)
                logger.info("💾 Total de eventos inseridos: %d", total_events_inserted)

                if batch_number >= max_batches:
                    logger.warning("⚠️ Atingido limite de %d batches - pode haver mais eventos", max_batches)

            except Exception as e:
                logger.warning("ATIVMOB skipped due to error: %s", e, exc_info=True)
        else:
            logger.info("ATIVMOB credentials not configured, skipping")

        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.info("=" * 80)
        logger.info("ATIVMOB Job Completed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)
        logger.info("=" * 80)

    except Exception:
        logger.exception("ATIVMOB Job failed with exception")
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        logger.error("ATIVMOB Job Failed at %s (duration: %.2f seconds)", job_end.isoformat(), duration)


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

    # JOB 2: InfoMarket (encartes/preços) - 3x por dia (00h, 12h, 16h)
    scheduler.add_job(
        run_infomarket_job,
        "cron",
        hour="0,12,16",
        minute=0,
        id="infomarket_job",
        name="InfoMarket - 3x ao dia",
    )

    # JOB 3: ATIVMOB Estoque - 3x por dia (00h, 12h, 16h)
    scheduler.add_job(
        run_ativmob_job,
        "cron",
        hour="0,12,16",
        minute=15,  # 15 minutos após InfoMarket para evitar sobrecarga
        id="ativmob_job",
        name="ATIVMOB Estoque - 3x ao dia",
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
