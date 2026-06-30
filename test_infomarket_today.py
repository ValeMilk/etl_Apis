import requests
import urllib3
from datetime import datetime, timedelta
urllib3.disable_warnings()

# Credenciais do InfoMarket
email = "valemilk@valemilk.com.br"
password = "51c3@2024"

print("Testando API InfoMarket hoje (22/06)...")
print("=" * 70)

# Login
login_url = "https://app.infomarketpesquisa.com/api/users/login"
login_resp = requests.post(
    login_url,
    headers={"Content-Type": "application/json"},
    json={"email": email, "password": password},
    verify=False,
    timeout=30
)
resp_data = login_resp.json()
token = (
    resp_data.get("accessToken")
    or resp_data.get("token")
    or resp_data.get("access_token")
    or resp_data.get("id")
)
if not token:
    print(f"❌ Login falhou. Campos retornados: {list(resp_data.keys())}")
    print(f"   Response: {resp_data}")
    exit(1)
print(f"✅ Token obtido: {token[:30]}...")

# Testar período de hoje
headers = {"Authorization": token}

print(f"\n📅 Testando período: 15/06 → 21/08")

start_str = "20260615"
finish_str = "20260821"
url = "https://app.infomarketpesquisa.com/api/leaflets/getPrices"

all_records = []
skip = 0
max_pages = 100

for page in range(max_pages):
    params = {
        "initialDate": start_str,
        "finalDate": finish_str,
        "skip": skip,
        "limit": 1000
    }
    
    resp = requests.get(
        url,
        params=params,
        headers=headers,
        verify=False,
        timeout=30
    )
    
    data = resp.json()
    records = data.get("records", [])
    
    if not records:
        print(f"   Página {page}: 0 registros → FIM")
        break
    
    all_records.extend(records)
    print(f"   Página {page}: {len(records)} registros (total: {len(all_records)})")
    
    if len(records) < 1000:
        break
    
    skip += 1000

print(f"\n📊 Resultado:")
print(f"   Total de registros: {len(all_records)}")

if all_records:
    # Extrair datas únicas
    datas = sorted(set([r.get("validity_start_date", "")[:10] for r in all_records]))
    print(f"   Datas presentes: {len(datas)} dias diferentes")
    print(f"   Período: {datas[0]} → {datas[-1]}")
    
    print(f"\n   Últimas 10 datas:")
    for data_str in datas[-10:]:
        count = len([r for r in all_records if r.get("validity_start_date", "")[:10] == data_str])
        print(f"      {data_str}: {count} registros")
