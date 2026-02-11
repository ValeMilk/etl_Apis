from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class VendaSchema:
    """Schema para registro de venda."""
    data: date
    loja_id: int
    nome_loja: Optional[str] = None
    cnpj_loja: Optional[str] = None
    ean: Optional[str] = None
    cod_interno: Optional[str] = None
    plu: Optional[int] = None
    produto: Optional[str] = None
    qtd: float = 0.0
    venda: float = 0.0
    custo: float = 0.0


@dataclass
class EstoqueSchema:
    """Schema para snapshot de estoque."""
    snapshot_ts: datetime
    loja_id: int
    codigo_produto: str
    descricao_produto: str
    ean: str
    estq_loja: int
    estq_avaria: int = 0
