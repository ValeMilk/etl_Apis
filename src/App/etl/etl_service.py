import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

from api_cometa import CometaClient
from App.core.database import DatabaseClient


class ETLService:
    def __init__(self, cometa_client: CometaClient, db_client: DatabaseClient) -> None:
        self.cometa_client = cometa_client
        self.db_client = db_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def processar_vendas(self) -> None:
        self.logger.info("Starting vendas ETL")
        lojas = self.cometa_client.list_lojas()
        if not lojas:
            self.logger.warning("No lojas found for vendas")
            return

        inicio_mes = datetime.now().replace(day=1)
        fim = datetime.now()
        todas_vendas: List[dict] = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            futuros = {
                executor.submit(self.cometa_client.get_vendas_loja, loja, inicio_mes, fim): loja
                for loja in lojas
            }
            for future in as_completed(futuros):
                loja_id = futuros[future]
                try:
                    vendas_loja = future.result()
                    todas_vendas.extend(vendas_loja)
                    self.logger.info("Loja %s: %s vendas", loja_id, len(vendas_loja))
                except Exception:
                    self.logger.exception("Failed to fetch vendas for loja %s", loja_id)

        if not todas_vendas:
            self.logger.warning("No vendas fetched")
            return

        self.db_client.upsert_vendas(todas_vendas)
        self.logger.info("Vendas ETL finished")

    def processar_estoque(self) -> None:
        self.logger.info("Starting estoque ETL")
        estoque = self.cometa_client.get_estoque()
        if not estoque:
            self.logger.warning("No estoque fetched")
            return

        self.db_client.replace_estoque(estoque)
        self.logger.info("Estoque ETL finished")

    def processar_tudo(self) -> None:
        self.processar_estoque()
        self.processar_vendas()
