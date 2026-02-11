"""Schemas de contrato de dados usando Pydantic para validação."""
from typing import Optional, List
from datetime import date

from pydantic import BaseModel, Field, field_validator


class VendaSchema(BaseModel):
    """Schema de uma venda individual desplanificada."""
    
    loja: Optional[int] = Field(None, alias="LOJA", description="ID da loja")
    id_loja: Optional[int] = Field(None, alias="ID_LOJA", description="ID da loja (alternativo)")
    nome_loja: Optional[str] = Field(None, alias="NOME_LOJA", description="Nome da loja")
    cnpj_loja: Optional[str] = Field(None, alias="CNPJ_LOJA", description="CNPJ da loja")
    data: Optional[date] = Field(None, alias="DATA", description="Data da venda")
    ean: Optional[str] = Field(None, alias="EAN", description="EAN do produto")
    cod_interno: Optional[str] = Field(None, alias="COD_INTERNO", description="Código interno")
    plu: Optional[int] = Field(None, alias="PLU", description="PLU do produto")
    produto: Optional[str] = Field(None, alias="PRODUTO", description="Nome do produto")
    qtd: Optional[float] = Field(None, alias="QTD", description="Quantidade vendida")
    venda: Optional[float] = Field(None, alias="VENDA", description="Valor total da venda")
    custo: Optional[float] = Field(None, alias="CUSTO", description="Custo unitário")
    
    @field_validator("loja", "id_loja", mode="before")
    @classmethod
    def coerce_int(cls, v):
        """Tenta converter para int se não for None."""
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    
    @field_validator("qtd", "venda", "custo", mode="before")
    @classmethod
    def coerce_float(cls, v):
        """Tenta converter para float se não for None."""
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    
    class Config:
        """Configuração do modelo."""
        populate_by_name = True  # Aceita tanto alias quanto field name
        extra = "ignore"  # Ignora campos extras


class EstoqueSchema(BaseModel):
    """Schema de um item de estoque."""
    
    loja: Optional[int] = Field(None, alias="LOJA", description="ID da loja")
    codigo_produto: Optional[str] = Field(None, alias="CODIGO_PRODUTO", description="Código do produto")
    descricao_produto: Optional[str] = Field(None, alias="DESCRICAO_PRODUTO", description="Descrição do produto")
    ean: Optional[str] = Field(None, alias="EAN", description="EAN do produto")
    estq_loja: Optional[int] = Field(None, alias="ESTQ_LOJA", description="Estoque na loja")
    estq_avaria: Optional[int] = Field(None, alias="ESTQ_AVARIA", description="Estoque em avaria")
    
    @field_validator("loja", "estq_loja", "estq_avaria", mode="before")
    @classmethod
    def coerce_int(cls, v):
        """Tenta converter para int se não for None."""
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    
    class Config:
        """Configuração do modelo."""
        populate_by_name = True
        extra = "ignore"


class LojaSchema(BaseModel):
    """Schema de informações da loja."""
    
    loja: Optional[int] = Field(None, alias="LOJA", description="ID da loja")
    nome: Optional[str] = Field(None, alias="NOME", description="Nome da loja")
    cnpj: Optional[str] = Field(None, alias="CNPJ", description="CNPJ da loja")
    
    @field_validator("loja", mode="before")
    @classmethod
    def coerce_int(cls, v):
        """Tenta converter para int."""
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    
    class Config:
        """Configuração do modelo."""
        populate_by_name = True
        extra = "ignore"
