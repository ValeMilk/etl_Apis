#!/usr/bin/env python
"""Listar tabelas do banco"""
from App.core.database import DatabaseClient
from App.core.config import settings
from sqlalchemy import text

db = DatabaseClient(settings.db_url)

with db.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name
    """))
    
    print("\n📋 TABELAS NO BANCO:")
    for row in result:
        print(f"   - {row[0]}")
