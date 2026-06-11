#!/usr/bin/env python3
"""
Bootstrap script para inicialização única do banco de dados.

Carrega histórico de vendas desde 01/01/2025 ou customizado.
Usa detecção automática para rodar apenas uma vez.

Uso via CLI:
    python bootstrap.py
    python bootstrap.py --year 2024

Uso via Docker:
    Automático via entrypoint-etl.sh
"""

import sys
import logging
from datetime import datetime, date, timedelta
from typing import Optional

sys.path.insert(0, '/app')

from sqlalchemy import text

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | Bootstrap | %(message)s'
)
logger = logging.getLogger("Bootstrap")


class Bootstrap:
    """Gerencia inicialização única do banco."""

    def __init__(self):
        try:
            from App.core.config import settings
            from api_cometa import CometaClient
            from App.core.database import DatabaseClient
            from App.etl.etl_service import ETLService

            self.settings = settings
            self.cometa_client = CometaClient(
                base_url=settings.api_base_url,
                email=settings.api_email,
                password=settings.api_password.get_secret_value(),
                timeout=settings.request_timeout,
                verify_ssl=settings.verify_ssl,
                token_refresh_hours=settings.token_refresh_hours,
            )
            self.db_client = DatabaseClient(
                db_url=settings.db_url,
                echo=False
            )
            self.etl_service = ETLService(self.cometa_client, self.db_client)

            # ValeFish
            self.etl_service_valefish = None
            if settings.valefish_api_email:
                self.cometa_client_valefish = CometaClient(
                    base_url=settings.api_base_url,
                    email=settings.valefish_api_email,
                    password=settings.valefish_api_password.get_secret_value(),
                    timeout=settings.request_timeout,
                    verify_ssl=settings.verify_ssl,
                    token_refresh_hours=settings.token_refresh_hours,
                )
                self.etl_service_valefish = ETLService(self.cometa_client_valefish, self.db_client, target="valefish")
                logger.info("✅ ValeFish clients initialized")

            logger.info("✅ All clients initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}", exc_info=True)
            raise

    def is_bootstrap_needed(self) -> bool:
        """Verifica se banco precisa de bootstrap."""
        try:
            with self.db_client.get_session() as session:
                # Verifica se tabela vendas existe
                result = session.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name='vendas'"
                    )
                ).scalar()

                if not result:
                    logger.info("❌ Tabela 'vendas' não existe - Bootstrap necessário")
                    return True

                # Conta vendas
                count = session.execute(text("SELECT COUNT(*) FROM vendas")).scalar() or 0

                if count == 0:
                    logger.info("❌ Tabela 'vendas' está vazia - Bootstrap necessário")
                    return True

                logger.info(f"✅ Banco já possui {count} vendas - Bootstrap desnecessário")
                return False

        except Exception as e:
            logger.warning(f"Erro ao verificar status: {e}")
            # Se erro, assume que bootstrap é necessário
            return True

    def run(self, year: int = 2025) -> bool:
        """Executa bootstrap."""
        if not self.is_bootstrap_needed():
            logger.info("Bootstrap skipped - database already initialized")
            return True

        try:
            logger.info("=" * 70)
            logger.info("BOOTSTRAP: Initializing database with historical data")
            logger.info(f"Year: {year}")
            logger.info("=" * 70)

            # Contagem antes
            vendas_antes = 0
            try:
                with self.db_client.get_session() as session:
                    vendas_antes = session.execute(
                        text("SELECT COUNT(*) FROM vendas")
                    ).scalar() or 0
            except Exception as e:
                logger.warning(f"Could not count vendas before bootstrap: {e}")

            logger.info(f"Vendas before: {vendas_antes}")
            logger.info("")

            # Coleta de vendas (histórico de 3 em 3 dias desde 02/11/2022)
            logger.info("📊 Collecting vendas (3-day windows from 02/11/2022)...")
            self.etl_service.bootstrap_vendas(
                data_inicio=datetime(2022, 11, 2),
                data_fim=datetime.now() - timedelta(days=1)  # API tem dados até ontem
            )

            logger.info("")

            # Coleta de estoque
            logger.info("📦 Collecting estoque...")
            self.etl_service.processar_estoque()

            # ── ValeFish Bootstrap ──
            if self.etl_service_valefish:
                logger.info("")
                logger.info("🐟 Starting ValeFish bootstrap...")
                self.etl_service_valefish.bootstrap_vendas(
                    data_inicio=datetime(2025, 1, 1),
                    data_fim=datetime.now() - timedelta(days=1)  # API tem dados até ontem
                )
                self.etl_service_valefish.processar_estoque()
                logger.info("✅ ValeFish bootstrap completed")

            # Contagem depois
            vendas_depois = 0
            try:
                with self.db_client.get_session() as session:
                    vendas_depois = session.execute(
                        text("SELECT COUNT(*) FROM vendas")
                    ).scalar() or 0
            except Exception as e:
                logger.warning(f"Could not count vendas after bootstrap: {e}")

            vendas_carregadas = vendas_depois - vendas_antes

            logger.info("")
            logger.info("=" * 70)
            logger.info("✅ BOOTSTRAP COMPLETED")
            logger.info(f"Vendas loaded: {vendas_carregadas}")
            logger.info(f"Total in database: {vendas_depois}")
            logger.info("=" * 70)

            return True

        except Exception as e:
            logger.error(f"❌ BOOTSTRAP FAILED: {e}", exc_info=True)
            return False


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Bootstrap BI_COMETA database with historical data"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Year to load data from (default: 2025)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force bootstrap even if database exists"
    )

    args = parser.parse_args()

    try:
        bootstrap = Bootstrap()

        # Se --force, roda sem verificação
        if args.force:
            logger.warning("⚠️  Forcing bootstrap (--force flag)")
            success = bootstrap.run(year=args.year)
        else:
            success = bootstrap.run(year=args.year)

        if success:
            logger.info("Bootstrap finished successfully")
            sys.exit(0)
        else:
            logger.error("Bootstrap failed!")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

