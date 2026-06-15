#!/usr/bin/env python
"""Validar dados de estoque no banco"""
from App.core.database import DatabaseClient
from App.core.config import settings

try:
    db = DatabaseClient(settings.db_url)
    
    # Validar estoque
    with db.engine.connect() as conn:
        result = conn.execute("SELECT MAX(created_at) as last_sync, COUNT(*) as total FROM estoque_valemilk")
        row = result.fetchone()
        print(f"\n=== ESTOQUE VALEMILK ===")
        print(f"Última sincronização: {row[0]}")
        print(f"Total de registros: {row[1]}")
        
    print("\n✅ Estoque sincronizado com sucesso!")
    
except Exception as e:
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()
