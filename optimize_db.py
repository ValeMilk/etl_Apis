#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')

from App.core.database import DatabaseClient
from App.core.config import settings
from sqlalchemy import text

db = DatabaseClient(settings.db_url)

print("🔧 Criando índices para otimização...")
print("=" * 60)

create_indexes = [
    ("Índice em vendas.data", 
     "CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas(data DESC)"),
    
    ("Índice em vendas.loja_id", 
     "CREATE INDEX IF NOT EXISTS idx_vendas_loja_id ON vendas(loja_id)"),
    
    ("Índice em vendas.created_at", 
     "CREATE INDEX IF NOT EXISTS idx_vendas_created_at ON vendas(created_at DESC)"),
    
    ("Índice em estoque.snapshot_ts", 
     "CREATE INDEX IF NOT EXISTS idx_estoque_snapshot_ts ON estoque(snapshot_ts DESC)"),
    
    ("Índice em estoque.loja_id", 
     "CREATE INDEX IF NOT EXISTS idx_estoque_loja_id ON estoque(loja_id)"),
    
    ("Índice em vendas_valefish.data", 
     "CREATE INDEX IF NOT EXISTS idx_vendas_valefish_data ON vendas_valefish(data DESC)"),
    
    ("Índice em vendas_valefish.loja_id", 
     "CREATE INDEX IF NOT EXISTS idx_vendas_valefish_loja_id ON vendas_valefish(loja_id)"),
    
    ("Índice em estoque_valefish.snapshot_ts", 
     "CREATE INDEX IF NOT EXISTS idx_estoque_valefish_snapshot_ts ON estoque_valefish(snapshot_ts DESC)"),
    
    ("Índice em infomarket.validity_start_date", 
     "CREATE INDEX IF NOT EXISTS idx_infomarket_validity_start ON infomarket(validity_start_date DESC)"),
    
    ("Índice em infomarket.network_id", 
     "CREATE INDEX IF NOT EXISTS idx_infomarket_network_id ON infomarket(network_id)"),
]

with db.engine.connect() as conn:
    for desc, query_str in create_indexes:
        try:
            print(f"✅ {desc}...")
            conn.execute(text(query_str))
            conn.commit()
        except Exception as e:
            print(f"⚠️  {desc}: {str(e)[:60]}")

print("\n" + "=" * 60)
print("✅ Índices criados com sucesso!")
print("\n📊 Vacuum para otimizar...")

try:
    conn = db.engine.connect()
    # VACUUM ANALYZE para otimizar
    conn.execute(text("VACUUM ANALYZE vendas;"))
    conn.execute(text("VACUUM ANALYZE estoque;"))
    conn.execute(text("VACUUM ANALYZE vendas_valefish;"))
    conn.execute(text("VACUUM ANALYZE estoque_valefish;"))
    conn.execute(text("VACUUM ANALYZE infomarket;"))
    conn.commit()
    conn.close()
    print("✅ VACUUM ANALYZE concluído!")
except Exception as e:
    print(f"⚠️  VACUUM: {e}")

print("\n" + "=" * 60)
print("🚀 Otimização concluída! Agora teste o Power BI novamente.")
