import logging
from contextlib import contextmanager
from datetime import datetime, date
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    Text,
    select,
    delete,
    insert,
    text,
)
from sqlalchemy.orm import sessionmaker


class DatabaseClient:
    def __init__(self, db_url: str, echo: bool = False) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.engine = create_engine(db_url, echo=echo, pool_pre_ping=True, future=True)
        self.metadata = MetaData()

        self.vendas = Table(
            "vendas",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("data", Date, nullable=False),
            Column("loja_id", Integer, nullable=False),
            Column("nome_loja", String(255), nullable=True),
            Column("cnpj_loja", String(18), nullable=True),
            Column("ean", String(20), nullable=True),
            Column("cod_interno", String(50), nullable=True),
            Column("plu", Integer, nullable=True),
            Column("produto", String(500), nullable=True),
            Column("qtd", Float, nullable=False, default=0.0),
            Column("venda", Float, nullable=False, default=0.0),
            Column("custo", Float, nullable=False, default=0.0),
            Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
        )

        self.estoque = Table(
            "estoque",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("snapshot_ts", DateTime, default=datetime.utcnow, nullable=False),
            Column("loja_id", Integer, nullable=False),
            Column("codigo_produto", String(50), nullable=False),
            Column("descricao_produto", String(500), nullable=False),
            Column("ean", String(20), nullable=True),
            Column("estq_loja", Integer, nullable=False, default=0),
            Column("estq_avaria", Integer, nullable=False, default=0),
        )

        # ValeFish tables (same structure)
        self.vendas_valefish = Table(
            "vendas_valefish",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("data", Date, nullable=False),
            Column("loja_id", Integer, nullable=False),
            Column("nome_loja", String(255), nullable=True),
            Column("cnpj_loja", String(18), nullable=True),
            Column("ean", String(20), nullable=True),
            Column("cod_interno", String(50), nullable=True),
            Column("plu", Integer, nullable=True),
            Column("produto", String(500), nullable=True),
            Column("qtd", Float, nullable=False, default=0.0),
            Column("venda", Float, nullable=False, default=0.0),
            Column("custo", Float, nullable=False, default=0.0),
            Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
        )

        self.estoque_valefish = Table(
            "estoque_valefish",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("snapshot_ts", DateTime, default=datetime.utcnow, nullable=False),
            Column("loja_id", Integer, nullable=False),
            Column("codigo_produto", String(50), nullable=False),
            Column("descricao_produto", String(500), nullable=False),
            Column("ean", String(20), nullable=True),
            Column("estq_loja", Integer, nullable=False, default=0),
            Column("estq_avaria", Integer, nullable=False, default=0),
        )

        self.infomarket = Table(
            "infomarket",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("price_id", String(50), nullable=False),
            Column("item_id", String(50), nullable=True),
            Column("description", String(500), nullable=True),
            Column("eans", String(500), nullable=True),
            Column("leaflet_id", String(50), nullable=True),
            Column("number_of_pages", Integer, nullable=True),
            Column("leaflet_name", String(255), nullable=True),
            Column("leaflet_type", String(100), nullable=True),
            Column("delivery_channel", String(100), nullable=True),
            Column("store_id", String(50), nullable=True),
            Column("store_name", String(255), nullable=True),
            Column("value", Float, nullable=True),
            Column("validity_start_date", Date, nullable=True),
            Column("validity_finish_date", Date, nullable=True),
            Column("dynamic", String(100), nullable=True),
            Column("minimum_quantity", Integer, nullable=True),
            Column("details", Text, nullable=True),
            Column("page", Integer, nullable=True),
            Column("city_name", String(255), nullable=True),
            Column("city_id", String(50), nullable=True),
            Column("network_id", String(50), nullable=True),
            Column("network_name", String(255), nullable=True),
            Column("brand_id", String(50), nullable=True),
            Column("brand_name", String(255), nullable=True),
            Column("identifier", String(100), nullable=True, unique=True),
            Column("store_cnpj", String(20), nullable=True),
            Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
        )

        self.ativmob_estoque = Table(
            "ativmob_estoque",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("event_id", String(50), nullable=False, unique=True),  # ID único do evento
            Column("store_cnpj", String(20), nullable=False),
            Column("event_code", String(50), nullable=False),
            Column("event_title", String(255), nullable=True),
            Column("event_dth", DateTime, nullable=False),  # Data/hora do evento
            Column("order_number", String(100), nullable=True),
            Column("invoice_number", String(100), nullable=True),
            Column("codigo_orcamento", String(100), nullable=True),
            Column("agent_code", String(50), nullable=True),
            Column("agent_name", String(255), nullable=True),
            Column("lat", String(50), nullable=True),
            Column("lng", String(50), nullable=True),
            Column("codigo_roteiro", String(100), nullable=True),
            Column("link_rastreamento", String(500), nullable=True),
            Column("razao_social_dest", String(500), nullable=True),
            Column("nome_fantasia_dest", String(500), nullable=True),
            Column("codigo_destino", String(50), nullable=True),
            # Campos desnormalizados do form[] para facilitar queries
            Column("produto_nome", String(500), nullable=True),
            Column("produto_codigo", String(50), nullable=True),
            Column("quantidade", Integer, nullable=True),
            Column("data_validade", Date, nullable=True),
            Column("em_ruptura", String(10), nullable=True),  # "SIM" ou "NÃO"
            # JSON completo do form[] para auditoria
            Column("form_json", Text, nullable=True),
            Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
        )

        self.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            self.logger.exception("Database transaction failed")
            raise
        finally:
            session.close()

    def upsert_vendas(self, vendas: Iterable[dict]) -> Tuple[int, int]:
        """
        Deleta todas as vendas das datas presentes e insere o novo lote.
        Garante idempotência: uma execução com os mesmos dados resulta no mesmo estado.
        """
        rows, date_range = self._prepare_vendas_rows(vendas)
        if not rows:
            self.logger.info("No vendas rows to upsert")
            return 0, 0

        min_date, max_date = date_range
        deleted = 0
        inserted = 0

        with self.get_session() as session:
            delete_stmt = delete(self.vendas).where(self.vendas.c.data.between(min_date, max_date))
            result = session.execute(delete_stmt)
            deleted = result.rowcount or 0

            session.execute(insert(self.vendas), rows)
            inserted = len(rows)

        self.logger.info("Upserted vendas. Deleted=%s Inserted=%s", deleted, inserted)
        return deleted, inserted

    def replace_estoque(self, estoque: Iterable[dict]) -> Tuple[int, int]:
        """
        Deleta todo estoque anterior e insere novo snapshot.
        Garante apenas o estoque mais recente no banco.
        """
        rows = self._prepare_estoque_rows(estoque)
        if not rows:
            self.logger.info("No estoque rows to replace")
            return 0, 0

        deleted = 0
        inserted = 0

        with self.get_session() as session:
            result = session.execute(delete(self.estoque))
            deleted = result.rowcount or 0
            session.execute(insert(self.estoque), rows)
            inserted = len(rows)

        self.logger.info("Replaced estoque. Deleted=%s Inserted=%s", deleted, inserted)
        return deleted, inserted

    def fetch_vendas(self, limit: Optional[int] = None, offset: int = 0, days: Optional[int] = None) -> List[dict]:
        """
        Retorna todas as vendas ordenadas por data DESC e id DESC.
        
        Args:
            limit: Número máximo de registros (None = sem limite)
            offset: Pular N registros (para paginação)
            days: Filtrar últimos N dias (None = sem filtro)
        """
        from datetime import datetime, timedelta
        
        stmt = select(self.vendas).order_by(self.vendas.c.data.desc(), self.vendas.c.id.desc())
        
        if days:
            cutoff_date = datetime.utcnow().date() - timedelta(days=days)
            stmt = stmt.where(self.vendas.c.data >= cutoff_date)
        
        if offset > 0:
            stmt = stmt.offset(offset)
        
        if limit:
            stmt = stmt.limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [dict(row) for row in rows]

    def fetch_estoque(self, limit: Optional[int] = None) -> List[dict]:
        """
        Retorna snapshot atual de estoque ordenado por snapshot_ts DESC.
        Sem paginação para consumo BI.
        """
        stmt = select(self.estoque).order_by(
            self.estoque.c.snapshot_ts.desc(),
            self.estoque.c.loja_id.asc(),
            self.estoque.c.codigo_produto.asc(),
        )
        if limit:
            stmt = stmt.limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [dict(row) for row in rows]

    # ── ValeFish methods ──

    def upsert_vendas_valefish(self, vendas: Iterable[dict]) -> Tuple[int, int]:
        """Upsert vendas ValeFish (mesma lógica da ValeMilk)."""
        rows, date_range = self._prepare_vendas_rows(vendas)
        if not rows:
            self.logger.info("No vendas_valefish rows to upsert")
            return 0, 0

        min_date, max_date = date_range
        deleted = 0
        inserted = 0

        with self.get_session() as session:
            delete_stmt = delete(self.vendas_valefish).where(self.vendas_valefish.c.data.between(min_date, max_date))
            result = session.execute(delete_stmt)
            deleted = result.rowcount or 0
            session.execute(insert(self.vendas_valefish), rows)
            inserted = len(rows)

        self.logger.info("Upserted vendas_valefish. Deleted=%s Inserted=%s", deleted, inserted)
        return deleted, inserted

    def replace_estoque_valefish(self, estoque: Iterable[dict]) -> Tuple[int, int]:
        """Replace estoque ValeFish (mesma lógica da ValeMilk)."""
        rows = self._prepare_estoque_rows(estoque)
        if not rows:
            self.logger.info("No estoque_valefish rows to replace")
            return 0, 0

        deleted = 0
        inserted = 0

        with self.get_session() as session:
            result = session.execute(delete(self.estoque_valefish))
            deleted = result.rowcount or 0
            session.execute(insert(self.estoque_valefish), rows)
            inserted = len(rows)

        self.logger.info("Replaced estoque_valefish. Deleted=%s Inserted=%s", deleted, inserted)
        return deleted, inserted

    def fetch_vendas_valefish(self, limit: Optional[int] = None) -> List[dict]:
        """Retorna vendas ValeFish ordenadas por data DESC."""
        stmt = select(self.vendas_valefish).order_by(self.vendas_valefish.c.data.desc(), self.vendas_valefish.c.id.desc())
        if limit:
            stmt = stmt.limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [dict(row) for row in rows]

    def fetch_estoque_valefish(self, limit: Optional[int] = None) -> List[dict]:
        """Retorna estoque ValeFish ordenado por snapshot_ts DESC."""
        stmt = select(self.estoque_valefish).order_by(
            self.estoque_valefish.c.snapshot_ts.desc(),
            self.estoque_valefish.c.loja_id.asc(),
            self.estoque_valefish.c.codigo_produto.asc(),
        )
        if limit:
            stmt = stmt.limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [dict(row) for row in rows]

    def _prepare_vendas_rows(self, vendas: Iterable[dict]) -> Tuple[List[dict], Tuple[date, date]]:
        """Prepara linhas de venda para inserção no banco."""
        rows: List[dict] = []
        min_date: Optional[date] = None
        max_date: Optional[date] = None

        for item in vendas:
            venda_date = self._extract_date(item) or datetime.utcnow().date()
            loja_id = self._extract_loja_id(item)

            if loja_id is None:
                self.logger.warning("Skipping venda without loja_id")
                continue

            row = {
                "data": venda_date,
                "loja_id": loja_id,
                "nome_loja": item.get("NOME_LOJA"),
                "cnpj_loja": item.get("CNPJ_LOJA"),
                "ean": self._sanitize_ean(item.get("EAN")),
                "cod_interno": item.get("COD_INTERNO"),
                "plu": self._safe_int(item.get("PLU")),
                "produto": item.get("PRODUTO"),
                "qtd": self._safe_float(item.get("QTD"), 0.0),
                "venda": self._safe_float(item.get("VENDA"), 0.0),
                "custo": self._safe_float(item.get("CUSTO"), 0.0),
                "created_at": datetime.utcnow(),
            }
            rows.append(row)

            min_date = venda_date if min_date is None else min(min_date, venda_date)
            max_date = venda_date if max_date is None else max(max_date, venda_date)

        if min_date is None or max_date is None:
            today = datetime.utcnow().date()
            min_date = today
            max_date = today

        return rows, (min_date, max_date)

    def _prepare_estoque_rows(self, estoque: Iterable[dict]) -> List[dict]:
        """Prepara linhas de estoque para inserção no banco."""
        snapshot_ts = datetime.utcnow()
        rows: List[dict] = []

        for item in estoque:
            loja_id = self._extract_loja_id(item)
            codigo_produto = item.get("CODIGO_PRODUTO") or item.get("codigo_produto")
            descricao = item.get("DESCRICAO_PRODUTO") or item.get("descricao_produto")

            if loja_id is None or not codigo_produto:
                self.logger.warning("Skipping estoque item without loja_id or codigo_produto")
                continue

            row = {
                "snapshot_ts": snapshot_ts,
                "loja_id": loja_id,
                "codigo_produto": str(codigo_produto),
                "descricao_produto": str(descricao or ""),
                "ean": self._sanitize_ean(item.get("EAN") or item.get("ean")),
                "estq_loja": self._safe_int(item.get("ESTQ_LOJA") or item.get("estq_loja"), 0),
                "estq_avaria": self._safe_int(item.get("ESTQ_AVARIA") or item.get("estq_avaria"), 0),
            }
            rows.append(row)

        return rows

    @staticmethod
    def _extract_date(item: dict) -> Optional[date]:
        """Extrai data de vários formatos possíveis."""
        for key in ("DATA", "data", "Data"):
            if key in item and item[key]:
                value = str(item[key])
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _extract_loja_id(item: dict) -> Optional[int]:
        """Extrai ID da loja de várias chaves possíveis."""
        for key in ("ID_LOJA", "LOJA", "loja", "id_loja"):
            if key in item and item[key] is not None:
                try:
                    return int(item[key])
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _safe_int(value, default: int = None) -> Optional[int]:
        """Converte valor para int com segurança."""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Converte valor para float com segurança."""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _sanitize_ean(value, max_len: int = 20) -> Optional[str]:
        """
        Normaliza EAN para caber na coluna ean VARCHAR(20).
        A API Cometa às vezes retorna dois códigos colados por vírgula
        (ex: '7898200380885,0000001516029') — mantém só o primeiro e,
        por segurança, ainda corta em max_len para nunca estourar a coluna.
        """
        if value is None:
            return None
        ean = str(value).split(",")[0].strip()
        return ean[:max_len] or None

    # ── InfoMarket methods ────────────────────────────────────────────────────

    def replace_infomarket(self, records: Iterable[dict]) -> Tuple[int, int]:
        """
        Substitui registros InfoMarket do período buscado.
        Deleta pelo range de validity_start_date e reinsere.
        """
        rows, date_range = self._prepare_infomarket_rows(records)
        if not rows:
            self.logger.info("No infomarket rows to replace")
            return 0, 0

        min_date, max_date = date_range
        deleted = 0
        inserted = 0

        with self.get_session() as session:
            delete_stmt = delete(self.infomarket).where(
                self.infomarket.c.validity_start_date.between(min_date, max_date)
            )
            result = session.execute(delete_stmt)
            deleted = result.rowcount or 0
            session.execute(insert(self.infomarket), rows)
            inserted = len(rows)

        self.logger.info("Replaced infomarket. Deleted=%s Inserted=%s", deleted, inserted)
        return deleted, inserted

    def fetch_infomarket(self, limit: Optional[int] = None) -> List[dict]:
        """Retorna registros infomarket ordenados por validity_start_date DESC."""
        stmt = select(self.infomarket).order_by(
            self.infomarket.c.validity_start_date.desc(),
            self.infomarket.c.store_name.asc(),
        )
        if limit:
            stmt = stmt.limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [dict(row) for row in rows]

    def fetch_infomarket_tratado(self) -> List[dict]:
        """
        Retorna registros infomarket com tratamento de preços:
        - Remove preços "padrão" (maior preço quando há variação)
        - Deduplica por network mantendo registro mais recente
        
        Query com CTEs:
        1. preco_tratado: calcula menor/maior preço por grupo
        2. sem_preco_padrao: filtra preços padrão
        3. deduplicado_network: remove duplicatas por network
        """
        query = text("""
            WITH preco_tratado AS (
                SELECT 
                    *,
                    MIN(value) OVER (
                        PARTITION BY 
                            network_id,
                            brand_id,
                            item_id,
                            leaflet_id,
                            validity_start_date,
                            validity_finish_date
                    ) AS menor_preco,

                    MAX(value) OVER (
                        PARTITION BY 
                            network_id,
                            brand_id,
                            item_id,
                            leaflet_id,
                            validity_start_date,
                            validity_finish_date
                    ) AS maior_preco
                FROM public.infomarket
            ),

            sem_preco_padrao AS (
                SELECT *
                FROM preco_tratado
                WHERE NOT (
                    menor_preco <> maior_preco
                    AND value = maior_preco
                )
            ),

            deduplicado_network AS (
                SELECT 
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY 
                            network_id,
                            brand_id,
                            item_id,
                            leaflet_id,
                            validity_start_date,
                            validity_finish_date,
                            value
                        ORDER BY 
                            created_at DESC,
                            store_id
                    ) AS rn_network
                FROM sem_preco_padrao
            )

            SELECT 
                id,
                price_id,
                item_id,
                description,
                eans,
                leaflet_id,
                number_of_pages,
                leaflet_name,
                leaflet_type,
                delivery_channel,

                network_id,
                network_name,

                value,
                validity_start_date,
                validity_finish_date,
                dynamic,
                minimum_quantity,
                details,
                page,
                city_name,
                city_id,
                created_at,
                brand_id,
                brand_name,
                identifier

            FROM deduplicado_network
            WHERE rn_network = 1
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        result = [dict(row) for row in rows]
        self.logger.info(f"fetch_infomarket_tratado: query returned {len(rows)} rows, result has {len(result)} records")
        return result

    def _prepare_infomarket_rows(self, records: Iterable[dict]) -> Tuple[List[dict], Tuple[date, date]]:
        """Converte registros da API InfoMarket para linhas do banco."""
        rows: List[dict] = []
        min_date: Optional[date] = None
        max_date: Optional[date] = None
        now = datetime.utcnow()

        for item in records:
            price_id = item.get("price_id")
            if not price_id:
                self.logger.warning("Skipping infomarket item without price_id")
                continue

            # Converte datas do formato YYYYMMDD (int) para date
            start_date = self._parse_infomarket_date(item.get("validity_start_date"))
            finish_date = self._parse_infomarket_date(item.get("validity_finish_date"))

            # eans é lista — armazena como string separada por vírgula
            eans_raw = item.get("eans", [])
            eans_str = ",".join(str(e) for e in eans_raw) if isinstance(eans_raw, list) else str(eans_raw or "")

            row = {
                "price_id": str(price_id),
                "item_id": item.get("item_id"),
                "description": item.get("description"),
                "eans": eans_str or None,
                "leaflet_id": item.get("leaflet_id"),
                "number_of_pages": self._safe_int(item.get("number_of_pages")),
                "leaflet_name": item.get("leaflet_name"),
                "leaflet_type": item.get("leaflet_type"),
                "delivery_channel": item.get("delivery_channel"),
                "store_id": item.get("store_id"),
                "store_name": item.get("store_name"),
                "value": self._safe_float(item.get("value"), 0.0),
                "validity_start_date": start_date,
                "validity_finish_date": finish_date,
                "dynamic": item.get("dynamic"),
                "minimum_quantity": self._safe_int(item.get("minimum_quantity")),
                "details": str(item.get("details")) if item.get("details") is not None else None,
                "page": self._safe_int(item.get("page")),
                "city_name": item.get("city_name"),
                "city_id": item.get("city_id"),
                "network_id": item.get("network_id"),
                "network_name": item.get("network_name"),
                "brand_id": item.get("brand_id"),
                "brand_name": item.get("brand_name"),
                "identifier": item.get("identifier"),
                "store_cnpj": item.get("store_cnpj"),
                "created_at": now,
            }
            rows.append(row)

            if start_date:
                min_date = start_date if min_date is None else min(min_date, start_date)
                max_date = start_date if max_date is None else max(max_date, start_date)

        if min_date is None:
            today = datetime.utcnow().date()
            min_date = today
            max_date = today

        return rows, (min_date, max_date)  # type: ignore[return-value]

    def get_last_infomarket_date(self) -> Optional[date]:
        """
        Retorna a data mais recente sincronizada.
        
        ATENÇÃO: Este método retorna MAX(validity_finish_date), não validity_start_date.
        Para sincronização incremental, prefira usar janela fixa (ex: hoje - 7 dias).
        """
        stmt = select(self.infomarket.c.validity_finish_date).order_by(
            self.infomarket.c.validity_finish_date.desc()
        ).limit(1)
        
        with self.engine.connect() as conn:
            result = conn.execute(stmt).scalar()
        
        return result

    @staticmethod
    def _parse_infomarket_date(value) -> Optional[date]:
        """Converte YYYYMMDD (int ou str) para date. Retorna None se inválido."""
        if value is None:
            return None
        try:
            return datetime.strptime(str(int(value)), "%Y%m%d").date()
        except (ValueError, TypeError):
            return None

    # ── ATIVMOB Estoque ───────────────────────────────────────────────────────

    def insert_ativmob_estoque(self, events: Iterable[dict]) -> int:
        """
        Insere eventos de estoque ATIVMOB no banco.
        
        Ignora duplicados (event_id único).
        Retorna número de registros inseridos.
        """
        import json
        
        rows = []
        now = datetime.utcnow()

        for event in events:
            event_id = event.get("event_id")
            if not event_id:
                self.logger.warning("Skipping ATIVMOB event without event_id")
                continue

            # Parse event_dth "2026-06-10 07:42:01"
            event_dth_str = event.get("event_dth")
            try:
                event_dth = datetime.strptime(event_dth_str, "%Y-%m-%d %H:%M:%S") if event_dth_str else None
            except (ValueError, TypeError):
                event_dth = None

            # Extrair campos do form[] array
            form_data = event.get("form", [])
            produto_nome = None
            produto_codigo = None
            quantidade = None
            data_validade = None
            em_ruptura = None

            for field in form_data:
                label = field.get("label", "").lower()
                value = field.get("value")
                codigo = field.get("codigo")

                if "produto" in label and "ruptura" not in label:
                    produto_nome = value
                    produto_codigo = codigo
                elif "quantidade" in label:
                    try:
                        quantidade = int(value) if value else None
                    except (ValueError, TypeError):
                        quantidade = None
                elif "validade" in label:
                    # "20/06/2026" → date
                    try:
                        data_validade = datetime.strptime(value, "%d/%m/%Y").date() if value else None
                    except (ValueError, TypeError):
                        data_validade = None
                elif "ruptura" in label:
                    em_ruptura = value  # "SIM" ou "NÃO"

            row = {
                "event_id": str(event_id),
                "store_cnpj": event.get("storeCNPJ"),
                "event_code": event.get("event_code"),
                "event_title": event.get("event_title"),
                "event_dth": event_dth,
                "order_number": event.get("order_number"),
                "invoice_number": event.get("invoice_number"),
                "codigo_orcamento": event.get("codigo_orcamento"),
                "agent_code": event.get("agent_code"),
                "agent_name": event.get("agent_name"),
                "lat": event.get("lat"),
                "lng": event.get("lng"),
                "codigo_roteiro": event.get("codigo_roteiro"),
                "link_rastreamento": event.get("link_rastreamento"),
                "razao_social_dest": event.get("razao_social_dest"),
                "nome_fantasia_dest": event.get("nome_fantasia_dest"),
                "codigo_destino": event.get("codigo_destino"),
                "produto_nome": produto_nome,
                "produto_codigo": produto_codigo,
                "quantidade": quantidade,
                "data_validade": data_validade,
                "em_ruptura": em_ruptura,
                "form_json": json.dumps(form_data, ensure_ascii=False) if form_data else None,
                "created_at": now,
            }
            rows.append(row)

        if not rows:
            self.logger.info("No ATIVMOB estoque rows to insert")
            return 0

        # Inserir com IGNORE (duplicados event_id são descartados)
        inserted_count = 0
        with self.get_session() as session:
            for row in rows:
                try:
                    stmt = insert(self.ativmob_estoque).values(**row)
                    session.execute(stmt)
                    inserted_count += 1
                except Exception as e:
                    # Ignora constraint violations (event_id duplicado)
                    if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                        self.logger.debug("Skipping duplicate event_id=%s", row.get("event_id"))
                    else:
                        self.logger.warning("Error inserting ATIVMOB event_id=%s: %s", row.get("event_id"), e)

        self.logger.info("Inserted %d ATIVMOB estoque records (ignored %d duplicates)", 
                         inserted_count, len(rows) - inserted_count)
        return inserted_count
