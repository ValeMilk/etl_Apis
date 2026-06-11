import calendar
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
        ETL de vendas:
        - Mês anterior (lookback 5 dias): get_vendas_loja por loja (API exige filtro de loja para datas antigas)
        - Mês atual: get_vendas_periodo sem filtro de loja (API rejeita filtro de loja para datas recentes)
        """
        self.logger.info("Starting vendas ETL")

        hoje = datetime.now()
        inicio_mes_atual = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fim = hoje - timedelta(days=1)  # API tem dados até ontem
        todas_vendas: List[dict] = []

        # ── Lookback mês anterior (ex: 27-31/03) via get_vendas_loja por loja ──
        inicio_lookback = inicio_mes_atual - timedelta(days=5)
        if inicio_lookback.date() < inicio_mes_atual.date():
            fim_mes_anterior = inicio_mes_atual - timedelta(days=1)
            self.logger.info(
                "Fetching prev month vendas %s to %s (per loja)",
                inicio_lookback.date(), fim_mes_anterior.date()
            )
            lojas = self.cometa_client.list_lojas()
            if lojas:
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futuros = {
                        executor.submit(
                            self.cometa_client.get_vendas_loja, loja, inicio_lookback, fim_mes_anterior
                        ): loja
                        for loja in lojas
                    }
                    for future in as_completed(futuros):
                        try:
                            todas_vendas.extend(future.result())
                        except Exception:
                            self.logger.exception("Failed prev month vendas for loja %s", futuros[future])

        # ── Mês atual (ex: 01-02/04) via get_vendas_periodo sem filtro de loja ──
        if fim.date() >= inicio_mes_atual.date():
            self.logger.info(
                "Fetching current month vendas %s to %s (sem filtro de loja)",
                inicio_mes_atual.date(), fim.date()
            )
            vendas_mes_atual = self.cometa_client.get_vendas_periodo(inicio_mes_atual, fim)
            todas_vendas.extend(vendas_mes_atual)

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
