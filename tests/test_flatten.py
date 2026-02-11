"""Script de teste para validar estrutura e desplanificação de dados."""
import json
from datetime import datetime

from App.shared.utils import flatten_vendas, flatten_estoque


def test_flatten_vendas():
    """Testa desplanificação de vendas (dados aninhados -> dados planos)."""
    
    # Simulando resposta da API com dados aninhados
    vendas_aninhadas = [
        {
            "LOJA": {
                "LOJA": 3,
                "NOME": "03- OL PAIVA",
                "CNPJ": "06887668000340"
            },
            "VENDAS": [
                {
                    "LOJA": 3,
                    "DATA": "01/12/2025",
                    "EAN": "7898200380953",
                    "COD_INTERNO": "142289",
                    "PLU": 142289,
                    "PRODUTO": "Iog Vale Milk Bicamada 130G Morango",
                    "QTD": 6,
                    "VENDA": 22.74,
                    "CUSTO": 2.65
                },
                {
                    "LOJA": 3,
                    "DATA": "01/12/2025",
                    "EAN": "7898200380960",
                    "COD_INTERNO": "133495",
                    "PLU": 133495,
                    "PRODUTO": "Iog Vale Milk Natural 150G Integral",
                    "QTD": 1,
                    "VENDA": 3.49,
                    "CUSTO": 2.44
                }
            ]
        }
    ]
    
    # Desplanificar
    vendas_planas = flatten_vendas(vendas_aninhadas)
    
    # Validações
    assert len(vendas_planas) == 2, f"Expected 2 rows, got {len(vendas_planas)}"
    
    for venda in vendas_planas:
        assert "ID_LOJA" in venda
        assert "NOME_LOJA" in venda
        assert "CNPJ_LOJA" in venda
        assert "PRODUTO" in venda
        assert "QTD" in venda
        assert "VENDA" in venda
        assert "CUSTO" in venda
        # Não deve haver LOJA dict ou VENDAS array
        assert not isinstance(venda.get("LOJA"), dict)
    
    print("✓ Teste de flatten_vendas passou")
    print(f"  Entrada: {len(vendas_aninhadas)} grupos de loja")
    print(f"  Saída: {len(vendas_planas)} vendas planas")
    print(f"  Primeira venda:\n    {json.dumps(vendas_planas[0], indent=2, default=str)}")


def test_flatten_estoque():
    """Testa padronização de estoque."""
    
    estoque_bruto = [
        {
            "LOJA": 1,
            "CODIGO_PRODUTO": "134258",
            "DESCRICAO_PRODUTO": "Beb Lactea Vale Milk Polpa 540G",
            "EAN": "7898200380953",
            "ESTQ_LOJA": 11,
            "ESTQ_AVARIA": 2
        },
        {
            "LOJA": 1,
            "CODIGO_PRODUTO": "142287",
            "descricao_produto": "Coalhada Vale Milk 140G Desnatada",  # lowercase
            "ean": "7898200380915",  # lowercase
            "estq_loja": 9,  # lowercase
            "estq_avaria": 0  # lowercase
        }
    ]
    
    # Desplanificar/padronizar
    estoque_plano = flatten_estoque(estoque_bruto)
    
    # Validações
    assert len(estoque_plano) == 2, f"Expected 2 rows, got {len(estoque_plano)}"
    
    for item in estoque_plano:
        assert "LOJA" in item
        assert "CODIGO_PRODUTO" in item
        assert "DESCRICAO_PRODUTO" in item
        assert "EAN" in item
        assert "ESTQ_LOJA" in item
        assert "ESTQ_AVARIA" in item
    
    print("✓ Teste de flatten_estoque passou")
    print(f"  Entrada: {len(estoque_bruto)} itens (com inconsistências)")
    print(f"  Saída: {len(estoque_plano)} itens padronizados")
    print(f"  Primeiro item:\n    {json.dumps(estoque_plano[0], indent=2, default=str)}")


if __name__ == "__main__":
    print("=" * 70)
    print("TESTES DE DESPLANIFICAÇÃO DE DADOS")
    print("=" * 70)
    test_flatten_vendas()
    print()
    test_flatten_estoque()
    print("=" * 70)
    print("✓ Todos os testes passaram!")
    print("=" * 70)
