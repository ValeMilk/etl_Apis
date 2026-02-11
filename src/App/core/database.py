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
    select,
    delete,
    insert,
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

    def fetch_vendas(self, limit: Optional[int] = None) -> List[dict]:
        """
        Retorna todas as vendas ordenadas por data DESC e id DESC.
        Sem paginação para consumo BI.
        """
        stmt = select(self.vendas).order_by(self.vendas.c.data.desc(), self.vendas.c.id.desc())
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
                "ean": item.get("EAN"),
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
                "ean": item.get("EAN") or item.get("ean"),
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
