#!/usr/bin/env python
"""Relatório completo de sincronização de dados"""
from datetime import datetime
from App.core.database import DatabaseClient
from App.core.config import settings
from sqlalchemy import text

db = DatabaseClient(settings.db_url)

print("\n" + "="*80)
print("RELATÓRIO DE SINCRONIZAÇÃO - BI COMETA")
print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

# 1. Vendas ValeMilk
print("\n📊 VENDAS VALEMILK:")
with db.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            MAX(data) as ultima_venda,
            MAX(created_at) as ultima_sync
        FROM vendas_valemilk
    """))
    row = result.fetchone()
    print(f"   Total: {row[0]:,} registros")
    print(f"   Última venda: {row[1]}")
    print(f"   Última sync: {row[2]}")

# 2. Estoque ValeMilk
print("\n📦 ESTOQUE VALEMILK:")
with db.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            MAX(created_at) as ultima_sync,
            COUNT(DISTINCT loja) as num_lojas
        FROM estoque_valemilk
    """))
    row = result.fetchone()
    print(f"   Total: {row[0]:,} registros")
    print(f"   Última sync: {row[1]}")
    print(f"   Lojas: {row[2]}")

# 3. Vendas ValeFish
print("\n🐟 VENDAS VALEFISH:")
with db.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            MAX(data) as ultima_venda,
            MAX(created_at) as ultima_sync
        FROM vendas_valefish
    """))
    row = result.fetchone()
    print(f"   Total: {row[0]:,} registros")
    print(f"   Última venda: {row[1]}")
    print(f"   Última sync: {row[2]}")

# 4. Estoque ValeFish
print("\n📦 ESTOQUE VALEFISH:")
with db.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            MAX(created_at) as ultima_sync,
            COUNT(DISTINCT loja) as num_lojas
        FROM estoque_valefish
    """))
    row = result.fetchone()
    print(f"   Total: {row[0]:,} registros")
    print(f"   Última sync: {row[1]}")
    print(f"   Lojas: {row[2]}")

# 5. InfoMarket
print("\n📋 INFOMARKET:")
with db.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            MIN(validity_start_date) as primeira_data,
            MAX(validity_end_date) as ultima_data,
            MAX(created_at) as ultima_sync,
            COUNT(DISTINCT store_cnpj) as num_lojas
        FROM infomarket
    """))
    row = result.fetchone()
    print(f"   Total: {row[0]:,} registros")
    print(f"   Período: {row[1]} até {row[2]}")
    print(f"   Última sync: {row[3]}")
    print(f"   Lojas: {row[4]}")

print("\n" + "="*80)
print("FREQUÊNCIA DE SINCRONIZAÇÃO")
print("="*80)
print(f"⏱️  Intervalo configurado: {settings.etl_interval_minutes} minutos")

# Verificar última execução do ETL worker
with db.engine.connect() as conn:
    # Pegar registro mais recente de qualquer tabela
    result = conn.execute(text("""
        SELECT MAX(created_at) as last_etl
        FROM (
            SELECT MAX(created_at) as created_at FROM vendas_valemilk
            UNION ALL
            SELECT MAX(created_at) FROM estoque_valemilk
            UNION ALL
            SELECT MAX(created_at) FROM vendas_valefish
            UNION ALL
            SELECT MAX(created_at) FROM estoque_valefish
            UNION ALL
            SELECT MAX(created_at) FROM infomarket
        ) combined
    """))
    row = result.fetchone()
    last_etl = row[0]
    
    # Calcular tempo desde última sync
    if last_etl:
        tempo_desde = datetime.now() - last_etl.replace(tzinfo=None)
        horas = int(tempo_desde.total_seconds() // 3600)
        minutos = int((tempo_desde.total_seconds() % 3600) // 60)
        
        print(f"🕐 Última execução: {last_etl} ({horas}h {minutos}min atrás)")
        
        if tempo_desde.total_seconds() > settings.etl_interval_minutes * 60 * 2:
            print("⚠️  ATENÇÃO: ETL não sincroniza há mais de 2 ciclos!")
        else:
            print("✅ ETL funcionando normalmente")

print("="*80 + "\n")
