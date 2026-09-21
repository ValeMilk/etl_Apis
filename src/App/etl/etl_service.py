import calendar
import logging
from datetime import datetime, timedelta
from typing import List

from api_cometa import CometaClient
from App.core.database import DatabaseClient


class ETLService:
    """
    Orquestra extração, transformação e carga de dados.
    Busca dados da API Cometa e persiste em PostgreSQL.
    
    Args:
        cometa_client: Cliente para API Cometa (autenticado)
        db_client: Cliente de banco de dados
        target: 'valemilk' ou 'valefish' (define tabelas de destino)
    """

    def __init__(self, cometa_client: CometaClient, db_client: DatabaseClient, target: str = "valemilk") -> None:
        self.cometa_client = cometa_client
        self.db_client = db_client
        self.target = target
        self.logger = logging.getLogger(f"ETLService[{target}]")

    def processar_vendas(self) -> None:
        """
        ETL de vendas: busca só os ultimos 2 dias (ontem + anteontem).

        Antes buscava o mes inteiro + lookback de 5 dias por loja (~100
        requisicoes/dia por empresa) - a TI da Cometa bloqueou o acesso por
        excesso de chamadas. O "+1 dia de garantia" cobre o caso de a API
        ainda nao ter os dados de ontem prontos na hora em que o job roda.
        """
        self.logger.info("Starting vendas ETL (ultimos 2 dias)")

        hoje = datetime.now()
        ontem = hoje - timedelta(days=1)
        anteontem = hoje - timedelta(days=2)

        self.logger.info("Fetching vendas %s a %s", anteontem.date(), ontem.date())
        todas_vendas = self.cometa_client.get_vendas_periodo(anteontem, ontem)

        if not todas_vendas:
            self.logger.warning("No vendas fetched")
            return

        if self.target == "valefish":
            deleted, inserted = self.db_client.upsert_vendas_valefish(todas_vendas)
        else:
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
        if self.target == "valefish":
            deleted, inserted = self.db_client.replace_estoque_valefish(estoque)
        else:
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
            data_inicio: Data inicial (default: 02/11/2022)
            data_fim: Data final (default: hoje)
        """
        if data_inicio is None:
            data_inicio = datetime(2022, 11, 2)
        if data_fim is None:
            data_fim = datetime.now() - timedelta(days=1)  # API tem dados até ontem
            
        self.logger.info(f"🔄 Bootstrap vendas from {data_inicio.date()} to {data_fim.date()}")
        self.logger.info("⚠️  Puxando dados de 3 em 3 dias (limite da API), sem filtro de loja")
        
        total_requisicoes = 0
        total_vendas_inseridas = 0
        BATCH_WINDOWS = 30  # Upsert a cada 30 janelas (~90 dias) para evitar OOM
        batch_vendas: List[dict] = []

        # Loop de 3 em 3 dias
        data_atual = data_inicio
        while data_atual <= data_fim:
            # Limita ao menor de: 3 dias à frente, último dia do mês atual, data_fim
            # A API Cometa rejeita janelas que cruzam limite de mês
            ultimo_dia_mes = calendar.monthrange(data_atual.year, data_atual.month)[1]
            fim_mes = data_atual.replace(day=ultimo_dia_mes, hour=23, minute=59, second=59)
            data_chunk_fim = min(data_atual + timedelta(days=2), fim_mes, data_fim)

            self.logger.info(f"📅 Fetching {data_atual.date()} → {data_chunk_fim.date()}")

            vendas_periodo = self.cometa_client.get_vendas_periodo(data_atual, data_chunk_fim)
            batch_vendas.extend(vendas_periodo)

            total_requisicoes += 1
            self.logger.info(
                f"✅ Period {data_atual.date()} → {data_chunk_fim.date()}: {len(vendas_periodo)} vendas"
            )

            # Upsert em batch a cada BATCH_WINDOWS janelas para liberar memória
            if total_requisicoes % BATCH_WINDOWS == 0 and batch_vendas:
                self.logger.info(f"💾 Batch upsert: {len(batch_vendas)} vendas...")
                if self.target == "valefish":
                    _, inserted = self.db_client.upsert_vendas_valefish(batch_vendas)
                else:
                    _, inserted = self.db_client.upsert_vendas(batch_vendas)
                total_vendas_inseridas += inserted
                self.logger.info(f"💾 Batch upsert concluído: {inserted} inseridas (total: {total_vendas_inseridas})")
                batch_vendas = []

            data_atual = data_chunk_fim + timedelta(days=1)

        # Upsert do restante
        if batch_vendas:
            self.logger.info(f"💾 Final upsert: {len(batch_vendas)} vendas...")
            if self.target == "valefish":
                _, inserted = self.db_client.upsert_vendas_valefish(batch_vendas)
            else:
                _, inserted = self.db_client.upsert_vendas(batch_vendas)
            total_vendas_inseridas += inserted

        self.logger.info(
            "Vendas bootstrap finished. Total_windows=%d Total_rows=%d",
            total_requisicoes, total_vendas_inseridas
        )
