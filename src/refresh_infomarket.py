#!/usr/bin/env python3
"""
Refresh completo dos dados InfoMarket dos últimos 220 dias.

Arquitetura: Extract -> Deduplicate -> Load

    FASE 1 (EXTRACT):     busca TODOS os chunks da API e acumula em memória.
    FASE 2 (DEDUPLICATE): remove duplicados por `identifier` (a API retorna o
                          mesmo registro em chunks diferentes).
    FASE 3 (LOAD):        TRUNCATE + INSERT em batches (dataset já deduplicado,
                          então INSERT simples é suficiente e rápido).

O banco só é tocado (TRUNCATE) DEPOIS de toda a extração ter sucesso, evitando
qualquer janela de dados vazios ou perda parcial.
"""
import sys
import logging
import time
from datetime import datetime, timedelta

sys.path.insert(0, '/app')

from sqlalchemy import text, insert
from infomarket_client import InfomarketClient
from App.core.config import settings
from App.core.database import DatabaseClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger("RefreshInfoMarket")

# Configurações
DIAS_HISTORICO = 220        # Quantos dias para trás buscar
DIAS_FUTURO = 60            # Encartes futuros
CHUNK_DAYS = 30             # Tamanho de cada chunk (evita timeout da API)
BATCH_SIZE = 1000           # Registros por INSERT (evita statement gigante)
MAX_RETRIES = 3             # Tentativas por chunk em caso de 502/timeout


def get_date_chunks(start_date, end_date, chunk_days=CHUNK_DAYS):
    """Divide o período em chunks menores para evitar timeout da API."""
    chunks = []
    current = start_date
    while current < end_date:
        chunk_end = min(current + timedelta(days=chunk_days), end_date)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def fetch_with_retry(client, start_date, finish_date, max_retries=MAX_RETRIES):
    """Busca dados de um chunk com retry em caso de erro 502/timeout."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Tentativa {attempt}/{max_retries}: {start_date} → {finish_date}")
            records = client.get_prices(start_date, finish_date)
            logger.info(f"✅ {len(records)} registros recebidos")
            return records
        except Exception as e:
            is_transient = "502" in str(e) or "timeout" in str(e).lower()
            if is_transient and attempt < max_retries:
                wait = 10 * attempt
                logger.warning(f"⚠️ {e.__class__.__name__}, aguardando {wait}s antes de retry...")
                time.sleep(wait)
            else:
                raise
    return []


def extract_and_dedup(client, chunks):
    """
    FASE 1 — EXTRACT + DEDUP incremental.
    Busca todos os chunks e deduplica por `identifier` NA HORA, mantendo apenas
    a última ocorrência de cada. Isso evita acumular ~246k brutos + cópias na
    memória (que causava OOM Killer). Pico de memória fica no nº de únicos.
    Nada é escrito no banco nesta fase.
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info("FASE 1 — EXTRACT + DEDUP: buscando chunks e deduplicando na hora")
    logger.info("=" * 70)

    dedup = {}            # identifier -> record (última ocorrência vence)
    sem_identifier = []   # registros sem identifier (mantidos todos)
    total_brutos = 0

    for idx, (chunk_start, chunk_end) in enumerate(chunks, 1):
        logger.info("")
        logger.info(f"📦 CHUNK {idx}/{len(chunks)}: {chunk_start} → {chunk_end}")
        records = fetch_with_retry(client, chunk_start, chunk_end)
        total_brutos += len(records)
        for record in records:
            ident = record.get("identifier")
            if ident:
                dedup[ident] = record
            else:
                sem_identifier.append(record)
        logger.info(f"   Únicos até agora: {len(dedup) + len(sem_identifier)} "
                    f"(brutos vistos: {total_brutos})")
        if idx < len(chunks):
            time.sleep(3)  # respiro entre chunks

    unique_records = list(dedup.values()) + sem_identifier
    logger.info("")
    logger.info(f"✅ EXTRACT + DEDUP completo:")
    logger.info(f"   Registros brutos vistos: {total_brutos}")
    logger.info(f"   Registros únicos:        {len(unique_records)}")
    logger.info(f"   Duplicados descartados:  {total_brutos - len(unique_records)}")
    logger.info(f"   Sem identifier:          {len(sem_identifier)}")
    return unique_records


def load(db_client, unique_records):
    """
    FASE 2 — LOAD (prepare + insert em batches).
    TRUNCATE, depois para cada batch: prepara as linhas E insere imediatamente,
    descartando antes de ir pro próximo. Assim nunca mantemos duas cópias
    completas na memória (~220k registros x2), o que causava OOM no container
    de 1GB. Pico de memória = unique_records + 1 batch (1000 linhas).
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info("FASE 2 — LOAD: TRUNCATE + PREPARE/INSERT em batches (memory-safe)")
    logger.info("=" * 70)

    # TRUNCATE (só agora, com todos os dados já extraídos)
    with db_client.get_session() as session:
        session.execute(text("TRUNCATE TABLE infomarket RESTART IDENTITY CASCADE"))
    logger.info("   ✅ Tabela truncada")

    total = 0
    n_batches = (len(unique_records) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(unique_records), BATCH_SIZE):
        batch_records = unique_records[i:i + BATCH_SIZE]
        # prepara só este batch (não a lista inteira → evita dobrar memória)
        rows, _ = db_client._prepare_infomarket_rows(batch_records)
        if rows:
            with db_client.get_session() as session:
                session.execute(insert(db_client.infomarket), rows)
            total += len(rows)
        logger.info(f"   📝 Batch {i // BATCH_SIZE + 1}/{n_batches}: +{len(rows)} (total: {total})")

    logger.info(f"✅ LOAD completo: {total} registros inseridos")
    return total


def main():
    logger.info("=" * 80)
    logger.info(f"REFRESH INFOMARKET — últimos {DIAS_HISTORICO} dias")
    logger.info("=" * 80)

    try:
        db_client = DatabaseClient(db_url=settings.db_url, echo=False)
        infomarket_client = InfomarketClient(
            email=settings.infomarket_email,
            password=settings.infomarket_password.get_secret_value(),
            timeout=settings.request_timeout,
        )
        logger.info("✅ Clientes inicializados")

        hoje = datetime.now().date()
        start_date = hoje - timedelta(days=DIAS_HISTORICO)
        finish_date = hoje + timedelta(days=DIAS_FUTURO)
        chunks = get_date_chunks(start_date, finish_date)
        logger.info(f"📅 Período: {start_date} → {finish_date} "
                    f"({(finish_date - start_date).days} dias, {len(chunks)} chunks)")

        # Pipeline: Extract+Dedup -> Load (prepare+insert em batches)
        unique_records = extract_and_dedup(infomarket_client, chunks)
        if not unique_records:
            logger.error("❌ Nenhum registro retornado pela API. Banco NÃO foi alterado.")
            return 1

        total = load(db_client, unique_records)

        # Resumo final
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ REFRESH INFOMARKET COMPLETO")
        logger.info(f"📊 Registros únicos extraídos: {len(unique_records)}")
        logger.info(f"📊 Registros no banco:         {total}")
        logger.info(f"📅 Período: {start_date} → {finish_date}")
        logger.info("=" * 80)
        return 0

    except Exception:
        logger.error("❌ Erro durante refresh do InfoMarket", exc_info=True)
        logger.error("⚠️ Se a falha ocorreu na FASE 1 (EXTRACT), o banco NÃO foi alterado.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
