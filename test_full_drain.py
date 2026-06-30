import requests
import urllib3
from collections import defaultdict
urllib3.disable_warnings()

BASE_URL = "https://api5.ativmob.com.br/v2/orders/delivery"
API_KEY = "8a672537-8569-4129-b768-6b745717f452"
CNPJ = "02518353000294"
headers = {"X-API-Key": API_KEY}

print("🔄 Esvaziando TODA a fila de eventos (GET + ACK até não ter mais)")
print("=" * 70)
print()

all_events = []
batch = 0

while True:
    batch += 1
    
    # Step 1: GET eventos
    resp = requests.get(
        f"{BASE_URL}/get_events/",
        params={"storeCNPJ": CNPJ, "event_code": "estoque"},
        headers=headers,
        verify=False,
        timeout=30
    )
    data = resp.json()
    events = data.get("events", [])
    
    if not events:
        print(f"✅ Batch #{batch}: 0 eventos → FIM! Fila vazia.")
        break
    
    all_events.extend(events)
    
    first_dth = events[0].get("event_dth")
    last_dth = events[-1].get("event_dth")
    event_ids = [e.get("event_id") for e in events]
    
    print(f"📦 Batch #{batch}: {len(events)} eventos | {first_dth} → {last_dth}")
    
    # Step 2: ACK eventos (remove da fila)
    ack_resp = requests.post(
        f"{BASE_URL}/ack_events/",
        json={"storeCNPJ": CNPJ, "events_ids": event_ids},
        headers=headers,
        verify=False,
        timeout=30
    )
    
    if ack_resp.status_code == 200:
        print(f"   ✅ ACK confirmado para {len(event_ids)} eventos")
    else:
        print(f"   ⚠️  ACK falhou: {ack_resp.status_code}")
    
    print()

print()
print("=" * 70)
print(f"🎯 Total de eventos na fila: {len(all_events)}")

if all_events:
    # Encontrar range de datas
    dths = [e.get("event_dth") for e in all_events]
    dths_sorted = sorted(dths)
    
    print()
    print(f"📅 EVENTO MAIS ANTIGO: {dths_sorted[0]}")
    print(f"📅 EVENTO MAIS RECENTE: {dths_sorted[-1]}")
    
    # Contar por dia
    por_dia = defaultdict(int)
    for dth in dths:
        day = dth.split()[0]  # pega só a data
        por_dia[day] += 1
    
    print()
    print(f"📊 Distribuição por dia ({len(por_dia)} dias):")
    for day in sorted(por_dia.keys()):
        print(f"   {day}: {por_dia[day]:4d} eventos")
else:
    print("Fila estava vazia desde o início!")

print()
print("=" * 70)
print("⚠️  NOTA: Todos esses eventos foram CONFIRMADOS (ACK) e removidos da fila!")
