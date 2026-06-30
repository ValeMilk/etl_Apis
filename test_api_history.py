import requests
import urllib3
urllib3.disable_warnings()

url = "https://api5.ativmob.com.br/v2/orders/delivery/get_events/"
headers = {"X-API-Key": "8a672537-8569-4129-b768-6b745717f452"}
params = {"storeCNPJ": "02518353000294", "event_code": "estoque"}

print("Testando múltiplas chamadas SEM ACK para recuperar histórico...")
print("=" * 70)
print()

all_events = []
for batch in range(1, 100):
    resp = requests.get(url, params=params, headers=headers, verify=False, timeout=30)
    data = resp.json()
    events = data.get("events", [])
    
    if not events:
        print(f"Batch #{batch}: 0 eventos → FIM DO HISTÓRICO")
        break
    
    all_events.extend(events)
    
    first_dth = events[0].get("event_dth")
    last_dth = events[-1].get("event_dth")
    
    print(f"Batch #{batch}: {len(events)} eventos | Período: {first_dth} → {last_dth}")
    
    # Se retornar menos de 100, é a última batch
    if len(events) < 100:
        print(f"\nÚltima batch retornou {len(events)} eventos (< 100)")
        break

print()
print("=" * 70)
print(f"Total recuperado: {len(all_events)} eventos")

if all_events:
    # Encontrar range de datas
    dths = [e.get("event_dth") for e in all_events]
    dths_sorted = sorted(dths)
    print(f"Período COMPLETO: {dths_sorted[0]} → {dths_sorted[-1]}")
    
    # Contar por dia
    from collections import defaultdict
    por_dia = defaultdict(int)
    for dth in dths:
        day = dth.split()[0]  # pega só a data
        por_dia[day] += 1
    
    print()
    print("Distribuição por dia:")
    for day in sorted(por_dia.keys()):
        print(f"  {day}: {por_dia[day]} eventos")
