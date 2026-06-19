"""
Bootstrap ATIVMOB - Carrega histórico de 90 dias de eventos de estoque.

Este script deve ser executado UMA VEZ para carregar o histórico inicial.
Após o bootstrap, o ETL Worker mantém sincronização automática 3x ao dia.

A API ATIVMOB retorna até 100 eventos por chamada. Este script faz loop
até não haver mais eventos pendentes (quando retornar < 100 eventos).

Uso:
    docker exec bi_cometa_etl python3 bootstrap_ativmob.py
"""
import logging
import sys
from datetime import datetime
from typing import List

from App.core.config import Settings
from App.core.database import DatabaseClient
from ativmob_client import AtivmobClient

# Configurar logging detalhado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ATIVMOB_Bootstrap")


def main():
    """Bootstrap de eventos ATIVMOB dos últimos 90 dias."""
    bootstrap_start = datetime.now()
    logger.info("=" * 80)
    logger.info("🚀 ATIVMOB Bootstrap Started at %s", bootstrap_start.isoformat())
    logger.info("=" * 80)

    try:
        # Carregar configurações
        settings = Settings()
        
        if not hasattr(settings, 'ativmob_api_key') or not hasattr(settings, 'ativmob_store_cnpj'):
            logger.error("❌ Credenciais ATIVMOB não configuradas no .env")
            logger.error("   Adicione: ativmob_api_key e ativmob_store_cnpj")
            sys.exit(1)

        # Inicializar clientes
        db_client = DatabaseClient(db_url=settings.db_url, echo=False)
        ativmob_client = AtivmobClient(
            api_key=settings.ativmob_api_key,
            store_cnpj=settings.ativmob_store_cnpj,
            timeout=settings.request_timeout,
        )

        logger.info("📌 CNPJ: %s", settings.ativmob_store_cnpj)
        logger.info("📌 Event Code: estoque")
        logger.info("")

        # ── Loop para puxar TODOS os eventos pendentes ───────────────────────
        total_events_fetched = 0
        total_events_inserted = 0
        batch_number = 0
        max_batches = 500  # Limite de segurança (500 batches * 100 eventos = 50k eventos max)

        logger.info("🔄 Iniciando loop de extração (até retornar < 100 eventos)...")
        logger.info("")

        while batch_number < max_batches:
            batch_number += 1
            logger.info("─" * 80)
            logger.info("📦 BATCH #%d", batch_number)
            logger.info("─" * 80)

            # Step 1: Buscar até 100 eventos
            response = ativmob_client.get_events(event_code="estoque")
            events = response.get("events", [])
            max_num_events = response.get("maxNumEvents", 100)

            if not events:
                logger.info("✅ Nenhum evento pendente - Bootstrap completo!")
                break

            events_count = len(events)
            total_events_fetched += events_count
            logger.info("📥 Recebidos: %d eventos", events_count)

            # Step 2: Inserir no banco
            inserted_count = db_client.insert_ativmob_estoque(events)
            total_events_inserted += inserted_count
            logger.info("💾 Inseridos: %d eventos (ignorados %d duplicatas)", 
                       inserted_count, events_count - inserted_count)

            # Step 3: Enviar ACK para API
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
                logger.info("")
                logger.info("✅ Última batch retornou %d eventos (< %d) - Sem mais eventos pendentes!", 
                           events_count, max_num_events)
                break

            logger.info("🔄 Batch retornou %d eventos = continuar para próxima batch...", 
                       max_num_events)

        # ── Resumo Final ──────────────────────────────────────────────────────
        bootstrap_end = datetime.now()
        duration = (bootstrap_end - bootstrap_start).total_seconds()

        logger.info("")
        logger.info("=" * 80)
        logger.info("🎉 ATIVMOB Bootstrap Completed!")
        logger.info("=" * 80)
        logger.info("📦 Total de batches: %d", batch_number)
        logger.info("📥 Total de eventos recebidos: %d", total_events_fetched)
        logger.info("💾 Total de eventos inseridos: %d", total_events_inserted)
        logger.info("⏱️  Duração: %.2f segundos", duration)
        logger.info("=" * 80)

        if batch_number >= max_batches:
            logger.warning("⚠️ Atingido limite de %d batches - pode haver mais eventos", max_batches)
            logger.warning("   Execute novamente se necessário")

    except Exception:
        logger.exception("❌ Bootstrap failed with exception")
        bootstrap_end = datetime.now()
        duration = (bootstrap_end - bootstrap_start).total_seconds()
        logger.error("=" * 80)
        logger.error("❌ ATIVMOB Bootstrap Failed at %s (duration: %.2f seconds)", 
                    bootstrap_end.isoformat(), duration)
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
