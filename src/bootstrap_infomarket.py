"""
Bootstrap InfoMarket — carga inicial dos últimos 90 dias em lotes mensais.

Uso:
    docker exec bi_cometa_etl python bootstrap_infomarket.py
    docker exec bi_cometa_etl python bootstrap_infomarket.py --days 90 --chunk 30
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bootstrap_infomarket")


def main(lookback_days: int = 90, chunk_days: int = 30, lookahead_days: int = 0) -> None:
    from App.core.config import settings
    from App.core.database import DatabaseClient
    from infomarket_client import InfomarketClient

    db = DatabaseClient(settings.db_url)
    client = InfomarketClient(
        email=settings.infomarket_email,
        password=settings.infomarket_password.get_secret_value(),
    )

    hoje = datetime.now()

    # Monta lista de janelas: cada chunk_days dias, do mais antigo ao mais recente
    janelas = []
    cursor = hoje - timedelta(days=lookback_days)
    while cursor < hoje + timedelta(days=lookahead_days):
        fim_janela = min(cursor + timedelta(days=chunk_days - 1), hoje + timedelta(days=lookahead_days))
        janelas.append((cursor, fim_janela))
        cursor = fim_janela + timedelta(days=1)

    logger.info(
        "Bootstrap InfoMarket: %d dias lookback + %d dias lookahead → %d lotes de %d dias",
        lookback_days, lookahead_days, len(janelas), chunk_days,
    )

    total_inserido = 0

    for i, (inicio, fim) in enumerate(janelas, 1):
        logger.info(
            "Lote %d/%d: %s → %s",
            i, len(janelas), inicio.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d"),
        )
        try:
            records = client.get_prices(inicio, fim)
            if not records:
                logger.info("  Lote %d: nenhum registro retornado", i)
                continue

            deleted, inserted = db.replace_infomarket(records)
            total_inserido += inserted
            logger.info("  Lote %d: Deleted=%d Inserted=%d", i, deleted, inserted)

        except Exception as exc:
            logger.error("  Lote %d FALHOU: %s", i, exc)
            logger.info("  Continuando com próximo lote...")

    logger.info("Bootstrap concluído. Total inserido: %d registros", total_inserido)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap InfoMarket")
    parser.add_argument("--days", type=int, default=90, help="Dias de lookback (padrão: 90)")
    parser.add_argument("--chunk", type=int, default=30, help="Tamanho do lote em dias (padrão: 30)")
    parser.add_argument("--lookahead", type=int, default=0, help="Dias de lookahead (padrão: 0)")
    args = parser.parse_args()

    main(lookback_days=args.days, chunk_days=args.chunk, lookahead_days=args.lookahead)
