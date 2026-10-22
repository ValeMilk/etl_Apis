#!/usr/bin/env python3
"""Script para buscar leaflet_id e descobrir skip/página"""
import sys
sys.path.insert(0, '/app')

from App.core.database import DatabaseClient
from App.core.config import settings
from sqlalchemy import text

db = DatabaseClient(settings.db_url)

leaflet_id = "6a60e0dcd14f6bb7c6e233ca"

print(f"🔎 Buscando leaflet_id: {leaflet_id}")

# Primeiro, verificar se existe
with db.engine.connect() as conn:
    check_query = text("SELECT COUNT(*) FROM infomarket WHERE leaflet_id = :lid")
    count = conn.execute(check_query, {"lid": leaflet_id}).scalar()
    print(f"Total de registros encontrados: {count}")
    
    if count == 0:
        print(f"❌ Nenhum registro encontrado para {leaflet_id}")
        sys.exit(1)
    
    # Buscar uma amostra
    sample_query = text("""
        SELECT 
            id,
            leaflet_id,
            leaflet_name,
            validity_start_date,
            validity_finish_date,
            network_name,
            created_at
        FROM infomarket 
        WHERE leaflet_id = :leaflet_id
        LIMIT 1
    """)
    
    result = conn.execute(sample_query, {"leaflet_id": leaflet_id})
    row = result.fetchone()
    
    if row:
        print(f"\n✅ Leaflet encontrado!")
        print(f"   ID: {row[0]}")
        print(f"   LeafletID: {row[1]}")
        print(f"   Nome: {row[2]}")
        print(f"   Validade: {row[3]} ate {row[4]}")
        print(f"   Rede: {row[5]}")
        print(f"   Criado em: {row[6]}")
        
        # Agora calcular skip
        # Contar registros que vêm ANTES
        first_id = row[0]
        start_date = row[3]
        
        # Usar ROW_NUMBER para manter consistência com a ordenação da API
        position_query = text("""
            SELECT ROW_NUMBER() OVER (ORDER BY validity_start_date ASC, id ASC) - 1 as position
            FROM infomarket 
            WHERE id = :first_id
        """)
        
        position = conn.execute(position_query, {"first_id": first_id}).scalar()
        print(f"\n🔍 LOCALIZAÇÃO NA API:")
        print(f"   Posição absoluta: {position}")
        print(f"   Skip (para skip=N, use N={position // 1000 * 1000}): {position // 1000 * 1000}")
        print(f"   Página: {(position // 1000) + 1}")
        print(f"   Posição na página: {(position % 1000) + 1}/1000")
    else:
        print(f"❌ Erro ao buscar detalhes")
