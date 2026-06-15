#!/usr/bin/env python
"""Debug login da API Cometa"""
import requests
import logging
from App.core.config import settings

logging.basicConfig(level=logging.DEBUG)

email = settings.api_email
password = settings.api_password.get_secret_value()
base_url = settings.api_base_url

print(f"Email: {email}")
print(f"Base URL: {base_url}")
print(f"Password length: {len(password)}")

url_login = f"{base_url}/login"
print(f"Login URL: {url_login}")

payload = {"email": email, "password": password}
print(f"Payload: {payload}")

try:
    response = requests.post(
        url_login,
        json=payload,
        headers={"Content-Type": "application/json"},
        verify=False,  # Ignore SSL
        timeout=30,
    )
    print(f"\nStatus: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Text: {response.text[:500]}")
    print(f"Content: {response.content[:500]}")
    
    if response.status_code == 200:
        print(f"\n✅ Login OK! Token: {response.text.strip()[:50]}...")
    else:
        print(f"\n❌ Login failed with {response.status_code}")
        
except Exception as e:
    print(f"\n❌ Exception: {e}")
    import traceback
    traceback.print_exc()
