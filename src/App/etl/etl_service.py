import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List

from api_cometa import CometaClient
from App.core.database import DatabaseClient


class ETLService:
    """
    Orquestra extração, transformação e carga de dados.
    Busca dados da API Cometa e persiste em PostgreSQL.
    """

    def __init__(self, cometa_client: CometaClient, db_client: DatabaseClient) -> None:
        self.cometa_client = cometa_client
        self.db_client = db_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def processar_vendas(self) -> None:
        """
        ETL de vendas: busca lojas, extrai vendas mensais, desplanifica e upserta.
        """
        self.logger.info("Starting vendas ETL")
        lojas = self.cometa_client.list_lojas()
        if not lojas:
            self.logger.warning("No lojas found for vendas")
            return

        inicio_mes = datetime.now().replace(day=1)
        fim = datetime.now()
        todas_vendas: List[dict] = []
        lojas_sucesso = 0
        lojas_falha = 0

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
                    lojas_sucesso += 1
                    self.logger.info(
                        "Loja %s: %d vendas processadas (sucesso: %d/%d)",
                        loja_id, len(vendas_loja), lojas_sucesso, len(lojas)
                    )
                except Exception:
                    lojas_falha += 1
                    self.logger.exception(
                        "Failed to fetch vendas for loja %s (falha: %d/%d)",
                        loja_id, lojas_falha, len(lojas)
                    )

        self.logger.info(
            "Vendas collection summary: sucesso=%d, falha=%d, total_vendas=%d",
            lojas_sucesso, lojas_falha, len(todas_vendas)
        )

        if not todas_vendas:
            self.logger.warning("No vendas fetched after processing all lojas")
            return

        # Dados já saem desplanificados do cliente
        deleted, inserted = self.db_client.upsert_vendas(todas_vendas)
        self.logger.info(
            "Vendas ETL finished. Deleted=%d Inserted=%d Total_rows=%d",
            deleted, inserted, len(todas_vendas)
        )

    def processar_estoque(self) -> None:
        """
        ETL de estoque: busca snapshot atual, desplaniifica e substitui no banco.
        """
        self.logger.info("Starting estoque ETL")
        estoque = self.cometa_client.get_estoque()
        if not estoque:
            self.logger.warning("No estoque fetched")
            return

        # Dados já saem desplanificados do cliente
        deleted, inserted = self.db_client.replace_estoque(estoque)
        self.logger.info("Estoque ETL finished. Deleted=%d Inserted=%d Total_rows=%d", deleted, inserted, len(estoque))

    def processar_tudo(self) -> None:
        """Executa ambos ETLs em sequência."""
        self.processar_estoque()
        self.processar_vendas()

    def bootstrap_vendas(self, data_inicio: datetime = None, data_fim: datetime = None) -> None:
        """
        Bootstrap de vendas: puxe histórico completo de 3 em 3 dias.
        
        Respeita limite de 3 dias da API Cometa.
        
        Args:
            data_inicio: Data inicial (default: 01/01/2025)
            data_fim: Data final (default: hoje)
        """
        if data_inicio is None:
            data_inicio = datetime(2025, 1, 1)
        if data_fim is None:
            data_fim = datetime.now()
            
        self.logger.info(f"🔄 Bootstrap vendas from {data_inicio.date()} to {data_fim.date()}")
        self.logger.info("⚠️  Puxando dados de 3 em 3 dias (limite da API)")
        
        lojas = self.cometa_client.list_lojas()
        if not lojas:
            self.logger.warning("No lojas found for vendas bootstrap")
            return
            
        todas_vendas: List[dict] = []
        total_requisicoes = 0
        
        # Loop de 3 em 3 dias
        data_atual = data_inicio
        while data_atual <= data_fim:
            # Próx 3 dias (window máximo da API: dia D + 2 = 3 dias total)
            # data_fim calculado como data_atual + 2 dias (inclusive)
            data_chunk_fim = min(data_atual + timedelta(days=2), data_fim)
            
            self.logger.info(f"📅 Fetching {data_atual.date()} → {data_chunk_fim.date()}")
            
            lojas_sucesso = 0
            lojas_falha = 0
            vendas_periodo = 0
            
            with ThreadPoolExecutor(max_workers=8) as executor:
                futuros = {
                    executor.submit(self.cometa_client.get_vendas_loja, loja, data_atual, data_chunk_fim): loja
                    for loja in lojas
                }
                for future in as_completed(futuros):
                    loja_id = futuros[future]
                    try:
                        vendas_loja = future.result()
                        todas_vendas.extend(vendas_loja)
                        vendas_periodo += len(vendas_loja)
                        lojas_sucesso += 1
                    except Exception as e:
                        lojas_falha += 1
                        self.logger.warning(f"Failed to fetch vendas for loja {loja_id}: {e}")
            
            total_requisicoes += 1
            self.logger.info(
                f"✅ Period {data_atual.date()} → {data_chunk_fim.date()}: "
                f"{vendas_periodo} vendas (lojas: {lojas_sucesso} ok, {lojas_falha} falha)"
            )
            
            # Próximo dia é o dia seguinte ao fim do chunk atual
            data_atual = data_chunk_fim + timedelta(days=1)
        
        self.logger.info(f"✅ Bootstrap completed: {total_requisicoes} day-windows, {len(todas_vendas)} total vendas")
        
        if not todas_vendas:
            self.logger.warning("No vendas fetched during bootstrap")
            return
        
        # Upsert todos os dados
        deleted, inserted = self.db_client.upsert_vendas(todas_vendas)
        self.logger.info(
            "Vendas bootstrap finished. Deleted=%d Inserted=%d Total_rows=%d",
            deleted, inserted, len(todas_vendas)
        )
