#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')

from App.core.database import DatabaseClient
from App.core.config import settings
from sqlalchemy import text

db = DatabaseClient(settings.db_url)

print("=" * 60)
print("DIAGNÓSTICO DO BANCO DE DADOS")
print("=" * 60)

queries = {
    "Tamanho das tabelas": """
        SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
        FROM pg_tables WHERE schemaname='public'
        ORDER BY pg_total_relation_size(tablename::regclass) DESC
    """,
    
    "Contagem de registros": """
        SELECT 
            'vendas' as tabela, COUNT(*) as registros FROM vendas
        UNION ALL
        SELECT 'estoque', COUNT(*) FROM estoque
        UNION ALL
        SELECT 'vendas_valefish', COUNT(*) FROM vendas_valefish
        UNION ALL
        SELECT 'estoque_valefish', COUNT(*) FROM estoque_valefish
        UNION ALL
        SELECT 'infomarket', COUNT(*) FROM infomarket
        UNION ALL
        SELECT 'ativmob_estoque', COUNT(*) FROM ativmob_estoque
    """,
    
    "Locks ativas": """
        SELECT pid, usename, application_name, client_addr, state, query
        FROM pg_stat_activity
        WHERE state != 'idle'
    """,
    
    "Índices": """
        SELECT tablename, indexname FROM pg_indexes WHERE schemaname='public'
    """
}

with db.engine.connect() as conn:
    for title, query_str in queries.items():
        print(f"\n📊 {title}:")
        print("-" * 60)
        try:
            result = conn.execute(text(query_str))
            rows = result.fetchall()
            
            if not rows:
                print("  (nenhum resultado)")
            else:
                for row in rows:
                    if len(row) == 2:
                        print(f"  {row[0]:30} {str(row[1]):20}")
                    else:
                        print(f"  {row}")
                        
        except Exception as e:
            print(f"  ❌ Erro: {e}")

print("\n" + "=" * 60)
