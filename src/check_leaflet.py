"""
Verificar se o leaflet específico '6a4bd3a5f7c4c01002c67cb3' está no banco.
"""
import sys
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

from App.core.config import settings
from App.core.database import DatabaseClient

db_client = DatabaseClient(db_url=settings.db_url, echo=False)

leaflet_id = "6a4bd3a5f7c4c01002c67cb3"

query = text("""
    SELECT 
        COUNT(*) as total,
        MIN(validity_start_date) as min_date,
        MAX(validity_start_date) as max_date
    FROM public.infomarket 
    WHERE leaflet_id = :leaflet_id 
      AND network_name = 'COMETA'
""")

with db_client.engine.connect() as conn:
    result = conn.execute(query, {"leaflet_id": leaflet_id}).fetchone()
    
    print(f"Leaflet ID: {leaflet_id}")
    print(f"Total de registros no banco: {result[0]}")
    print(f"Min validity_start_date: {result[1]}")
    print(f"Max validity_start_date: {result[2]}")

if result[0] == 0:
    print("\n⚠️ Este leaflet NÃO ESTÁ no banco!")
    print("\n📋 Buscando leaflets COMETA que ESTÃO no banco (01/07-15/07):")
    
    query2 = text("""
        SELECT DISTINCT
            leaflet_id,
            leaflet_name,
            validity_start_date,
            validity_finish_date,
            COUNT(*) as items
        FROM public.infomarket
        WHERE network_name = 'COMETA'
          AND validity_start_date BETWEEN '2026-07-01' AND '2026-07-15'
        GROUP BY leaflet_id, leaflet_name, validity_start_date, validity_finish_date
        ORDER BY validity_start_date
    """)
    
    with db_client.engine.connect() as conn:
        results = conn.execute(query2).fetchall()
        
        if results:
            print(f"\n✅ Encontrados {len(results)} encartes COMETA:")
            for row in results:
                print(f"  - {row[0][:20]}... | {row[1][:30]} | {row[2]}→{row[3]} | {row[4]} itens")
        else:
            print("\n❌ NENHUM encarte COMETA com validity_start_date entre 01/07-15/07!")
