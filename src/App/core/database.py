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
    Date,
    DateTime,
    select,
    delete,
    insert,
)
from sqlalchemy.dialects.postgresql import JSONB
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
            Column("loja_id", Integer, nullable=True),
            Column("payload", JSONB, nullable=False),
            Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
        )

        self.estoque = Table(
            "estoque",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("snapshot_ts", DateTime, default=datetime.utcnow, nullable=False),
            Column("loja_id", Integer, nullable=True),
            Column("payload", JSONB, nullable=False),
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

    def fetch_vendas(self) -> List[dict]:
        stmt = select(self.vendas.c.payload, self.vendas.c.data, self.vendas.c.loja_id).order_by(
            self.vendas.c.data.desc(), self.vendas.c.id.desc()
        )
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        result: List[dict] = []
        for row in rows:
            payload = dict(row["payload"] or {})
            payload = self._merge_metadata(payload, row["data"], row["loja_id"])
            result.append(payload)
        return result

    def fetch_estoque(self) -> List[dict]:
        stmt = select(
            self.estoque.c.payload, self.estoque.c.snapshot_ts, self.estoque.c.loja_id
        ).order_by(self.estoque.c.snapshot_ts.desc(), self.estoque.c.id.desc())
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        result: List[dict] = []
        for row in rows:
            payload = dict(row["payload"] or {})
            payload = self._merge_metadata(payload, row["snapshot_ts"].date(), row["loja_id"])
            result.append(payload)
        return result

    def _prepare_vendas_rows(self, vendas: Iterable[dict]) -> Tuple[List[dict], Tuple[date, date]]:
        rows: List[dict] = []
        min_date: Optional[date] = None
        max_date: Optional[date] = None

        for item in vendas:
            venda_date = self._extract_date(item) or datetime.utcnow().date()
            loja_id = self._extract_loja_id(item)

            rows.append({
                "data": venda_date,
                "loja_id": loja_id,
                "payload": item,
                "created_at": datetime.utcnow(),
            })

            min_date = venda_date if min_date is None else min(min_date, venda_date)
            max_date = venda_date if max_date is None else max(max_date, venda_date)

        if min_date is None or max_date is None:
            today = datetime.utcnow().date()
            min_date = today
            max_date = today

        return rows, (min_date, max_date)

    def _prepare_estoque_rows(self, estoque: Iterable[dict]) -> List[dict]:
        snapshot_ts = datetime.utcnow()
        rows: List[dict] = []

        for item in estoque:
            loja_id = self._extract_loja_id(item)
            rows.append({
                "snapshot_ts": snapshot_ts,
                "loja_id": loja_id,
                "payload": item,
            })

        return rows

    def _extract_date(self, item: dict) -> Optional[date]:
        for key in ("DATA", "data", "Data"):
            if key in item and item[key]:
                value = str(item[key])
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
        return None

    def _extract_loja_id(self, item: dict) -> Optional[int]:
        for key in ("ID_LOJA", "LOJA", "loja", "id_loja"):
            if key in item and item[key] is not None:
                try:
                    return int(item[key])
                except (TypeError, ValueError):
                    return None
        return None

    def _merge_metadata(self, payload: dict, data_value: Optional[date], loja_id: Optional[int]) -> dict:
        if data_value and "DATA" not in payload and "data" not in payload:
            payload["DATA"] = data_value.strftime("%Y-%m-%d")
        if loja_id is not None and "ID_LOJA" not in payload and "id_loja" not in payload:
            payload["ID_LOJA"] = loja_id
        return payload
