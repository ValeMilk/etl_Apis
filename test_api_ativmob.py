import requests
import urllib3
urllib3.disable_warnings()

url = "https://api5.ativmob.com.br/v2/orders/delivery/get_events/"
headers = {"X-API-Key": "8a672537-8569-4129-b768-6b745717f452"}
params = {"storeCNPJ": "02518353000294", "event_code": "estoque"}

print("Testando API ATIVMOB...")
print()

resp = requests.get(url, params=params, headers=headers, verify=False, timeout=30)
data = resp.json()

print("API Response:")
print("=" * 60)
print(f"maxNumEvents: {data.get('maxNumEvents')}")
print(f"startDateTime: {data.get('startDateTime')}")
print(f"events count: {len(data.get('events', []))}")
print()

if data.get("events"):
    events = data["events"]
    print(f"Primeiro evento: {events[0].get('event_dth')} (ID: {events[0].get('event_id')})")
    print(f"Ultimo evento: {events[-1].get('event_dth')} (ID: {events[-1].get('event_id')})")
    print()
    print("Sample dos primeiros 3 eventos:")
    for i, event in enumerate(events[:3]):
        print(f"  #{i+1}: event_id={event.get('event_id')}, event_dth={event.get('event_dth')}")
else:
    print("Nenhum evento pendente na API")
