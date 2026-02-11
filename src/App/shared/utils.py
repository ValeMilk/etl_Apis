"""Funções utilitárias compartilhadas."""
import logging
from datetime import datetime, date
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


def _get_data_shape(data: Any, max_chars: int = 50) -> str:
    """
    Retorna uma representação do "shape" (forma/estrutura) do dado para logging.
    Útil para debugar mudanças silenciosas no contrato da API.
    """
    if data is None:
        return "None"
    
    data_type = type(data).__name__
    data_preview = str(data)[:max_chars]
    
    if isinstance(data, (dict, list)):
        if isinstance(data, dict):
            keys = list(data.keys())[:5]  # Primeiras 5 chaves
            return f"dict(keys={keys}, len={len(data)})"
        else:
            return f"list(len={len(data)}, first_item_type={type(data[0]).__name__ if data else 'empty'})"
    
    return f"{data_type}(preview='{data_preview}')"


def _unwrap_list(item: Any) -> Optional[Dict[str, Any]]:
    """
    Se o item é uma lista com um dicionário interno, extrai o dict.
    API às vezes retorna em format: [[{dict1}, {dict2}]] ao invés de [{dict1}, {dict2}]
    """
    if isinstance(item, list):
        if len(item) > 0 and isinstance(item[0], dict):
            return item[0]  # Unwrap: extrai primeiro item
        return None  # Lista vazia ou não contém dict
    return None  # Não é lista


def flatten_vendas(vendas_brutos: List[dict]) -> List[dict]:
    """
    Transforma vendas aninhadas em formato plano.
    
    Entrada: Lista com dicts contendo LOJA (dict) e VENDAS (list)
    Saída: Lista com cada venda como dict independente (desplanificado)
    
    Implementa tratamento defensivo:
    - Verifica tipo de cada item
    - Se lista, tenta unwrap (extração do dict interno)
    - Loga avisos com detalhe do shape do dado
    - Continua processamento mesmo com items inválidos
    """
    if not vendas_brutos:
        return []
    
    if not isinstance(vendas_brutos, list):
        logger.warning(
            "flatten_vendas received non-list input: shape=%s",
            _get_data_shape(vendas_brutos)
        )
        return []
    
    result: List[dict] = []
    itens_invalidos = 0
    
    for idx, item in enumerate(vendas_brutos):
        # Verificação de tipo rigorosa
        if item is None:
            logger.debug("flatten_vendas: item[%d] é None, pulando", idx)
            itens_invalidos += 1
            continue
        
        # Se é lista, tenta unwrap
        if isinstance(item, list):
            unwrapped = _unwrap_list(item)
            if unwrapped is None:
                logger.warning(
                    "flatten_vendas: item[%d] é lista vazia ou sem dict. shape=%s",
                    idx, _get_data_shape(item)
                )
                itens_invalidos += 1
                continue
            item = unwrapped  # Usa o dict desembrulhado
        
        # Se não é dict, invalida
        if not isinstance(item, dict):
            logger.warning(
                "flatten_vendas: item[%d] é tipo inválido. shape=%s. Esperado: dict ou list[dict]",
                idx, _get_data_shape(item)
            )
            itens_invalidos += 1
            continue
        
        # Extração defensiva da estrutura LOJA/VENDAS
        try:
            info_loja = item.get("LOJA", {})
            if isinstance(info_loja, list):
                # API retornou LOJA como lista - unwrap
                info_loja_unwrapped = _unwrap_list(info_loja)
                if info_loja_unwrapped is not None:
                    info_loja = info_loja_unwrapped
                else:
                    logger.warning(
                        "flatten_vendas: item[%d] LOJA é lista vazia/inválida. shape=%s",
                        idx, _get_data_shape(info_loja)
                    )
                    info_loja = {}
            elif not isinstance(info_loja, dict):
                logger.warning(
                    "flatten_vendas: item[%d] LOJA é tipo inválido: %s (esperado dict). Pulando.",
                    idx, _get_data_shape(info_loja)
                )
                itens_invalidos += 1
                continue
            
            vendas_list = item.get("VENDAS", [])
            if not isinstance(vendas_list, list):
                logger.warning(
                    "flatten_vendas: item[%d] VENDAS é tipo inválido: %s (esperado list). shape=%s",
                    idx, type(vendas_list).__name__, _get_data_shape(vendas_list)
                )
                vendas_list = []
            
            loja_id = info_loja.get("LOJA") or item.get("LOJA")
            nome_loja = info_loja.get("NOME")
            cnpj_loja = info_loja.get("CNPJ")
            
            # Processa cada venda
            for venda_idx, venda in enumerate(vendas_list):
                if not isinstance(venda, dict):
                    logger.warning(
                        "flatten_vendas: item[%d].VENDAS[%d] é tipo inválido: %s. shape=%s. Pulando item de venda.",
                        idx, venda_idx, type(venda).__name__, _get_data_shape(venda)
                    )
                    continue
                
                venda_flat = {
                    "LOJA": venda.get("LOJA") or loja_id,
                    "ID_LOJA": venda.get("LOJA") or loja_id,
                    "NOME_LOJA": nome_loja,
                    "CNPJ_LOJA": cnpj_loja,
                    "DATA": venda.get("DATA"),
                    "EAN": venda.get("EAN"),
                    "COD_INTERNO": venda.get("COD_INTERNO"),
                    "PLU": venda.get("PLU"),
                    "PRODUTO": venda.get("PRODUTO"),
                    "QTD": venda.get("QTD"),
                    "VENDA": venda.get("VENDA"),
                    "CUSTO": venda.get("CUSTO"),
                }
                result.append(venda_flat)
        
        except Exception as e:
            logger.error(
                "flatten_vendas: Erro ao processar item[%d]. shape=%s. Erro: %s",
                idx, _get_data_shape(item), str(e), exc_info=True
            )
            itens_invalidos += 1
            continue
    
    if itens_invalidos > 0:
        logger.warning(
            "flatten_vendas: Processamento concluído com %d items inválidos de %d. Retornando %d vendas válidas.",
            itens_invalidos, len(vendas_brutos), len(result)
        )
    
    return result


def flatten_estoque(estoque_brutos: List[dict]) -> List[dict]:
    """
    Padroniza estoque para formato com colunas esperadas.
    
    Implementa validação defensiva:
    - Verifica tipo de cada item
    - Loga avisos com detalhe de tipos inválidos
    - Continua processamento mesmo com items inválidos
    
    Esperado: LOJA, CODIGO_PRODUTO, DESCRICAO_PRODUTO, EAN, ESTQ_LOJA, ESTQ_AVARIA
    """
    if not estoque_brutos:
        return []
    
    if not isinstance(estoque_brutos, list):
        logger.warning(
            "flatten_estoque received non-list input: shape=%s",
            _get_data_shape(estoque_brutos)
        )
        return []
    
    result: List[dict] = []
    itens_invalidos = 0
    
    for idx, item in enumerate(estoque_brutos):
        # Validação de tipo
        if item is None:
            logger.debug("flatten_estoque: item[%d] é None, pulando", idx)
            itens_invalidos += 1
            continue
        
        # Se é lista, tenta unwrap
        if isinstance(item, list):
            unwrapped = _unwrap_list(item)
            if unwrapped is None:
                logger.warning(
                    "flatten_estoque: item[%d] é lista vazia ou sem dict. shape=%s",
                    idx, _get_data_shape(item)
                )
                itens_invalidos += 1
                continue
            item = unwrapped
        
        # Se não é dict, invalida
        if not isinstance(item, dict):
            logger.warning(
                "flatten_estoque: item[%d] é tipo inválido. shape=%s. Esperado: dict",
                idx, _get_data_shape(item)
            )
            itens_invalidos += 1
            continue
        
        try:
            item_flat = {
                "LOJA": item.get("LOJA") or item.get("loja"),
                "CODIGO_PRODUTO": item.get("CODIGO_PRODUTO") or item.get("codigo_produto"),
                "DESCRICAO_PRODUTO": item.get("DESCRICAO_PRODUTO") or item.get("descricao_produto"),
                "EAN": item.get("EAN") or item.get("ean"),
                "ESTQ_LOJA": item.get("ESTQ_LOJA") or item.get("estq_loja"),
                "ESTQ_AVARIA": item.get("ESTQ_AVARIA") or item.get("estq_avaria", 0),
            }
            result.append(item_flat)
        except Exception as e:
            logger.error(
                "flatten_estoque: Erro ao processar item[%d]. shape=%s. Erro: %s",
                idx, _get_data_shape(item), str(e), exc_info=True
            )
            itens_invalidos += 1
            continue
    
    if itens_invalidos > 0:
        logger.warning(
            "flatten_estoque: Processamento concluído com %d items inválidos de %d. Retornando %d items válidos.",
            itens_invalidos, len(estoque_brutos), len(result)
        )
    
    return result


def parse_date(value: Any) -> Optional[date]:
    """Parse data de múltiplos formatos."""
    if value is None:
        return None
        
    value_str = str(value).strip()
    
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value_str, fmt).date()
        except ValueError:
            continue
    
    return None


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Converte para int com segurança."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Converte para float com segurança."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
