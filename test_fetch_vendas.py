#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')

from App.core.database import DatabaseClient
from App.core.config import settings

print("🔍 Testando fetch_vendas...")

db = DatabaseClient(settings.db_url)

# Testar com limite pequeno
print("\n1️⃣ Teste com limit=10:")
try:
    vendas = db.fetch_vendas(limit=10)
    print(f"   ✅ Retornou {len(vendas)} registros")
    if vendas:
        print(f"   📊 Primeira venda: data={vendas[0].get('data')}, loja_id={vendas[0].get('loja_id')}")
except Exception as e:
    print(f"   ❌ Erro: {e}")

# Testar com limite médio
print("\n2️⃣ Teste com limit=1000:")
try:
    import time
    start = time.time()
    vendas = db.fetch_vendas(limit=1000)
    elapsed = time.time() - start
    print(f"   ✅ Retornou {len(vendas)} registros em {elapsed:.2f}s")
except Exception as e:
    print(f"   ❌ Erro: {e}")

# Testar sem limite (PERIGOSO com 543k registros)
print("\n3️⃣ Teste SEM limite (timeout 10s):")
try:
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Timeout de 10s atingido")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(10)
    
    start = time.time()
    vendas = db.fetch_vendas(limit=None)
    signal.alarm(0)
    elapsed = time.time() - start
    print(f"   ✅ Retornou {len(vendas)} registros em {elapsed:.2f}s")
    
except TimeoutError:
    print(f"   ⚠️  Timeout! Query demora mais de 10s")
except Exception as e:
    print(f"   ❌ Erro: {e}")

print("\n" + "="*60)
