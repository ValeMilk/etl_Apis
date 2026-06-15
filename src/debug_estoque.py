#!/usr/bin/env python
"""Debug GET /estoque com token"""
import requests
import logging
from App.core.config import settings
from api_cometa import CometaClient

logging.basicConfig(level=logging.DEBUG)

email = settings.api_email
password = settings.api_password.get_secret_value()
base_url = settings.api_base_url

print(f"Base URL: {base_url}")

# 1. Get token
url_login = f"{base_url}/login"
payload = {"email": email, "password": password}

print("\n=== STEP 1: Login ===")
try:
    response = requests.post(
        url_login,
        json=payload,
        headers={"Content-Type": "application/json"},
        verify=False,
        timeout=60,
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        token = response.text.strip()
        print(f"Token: {token[:50]}...")
    else:
        print(f"Error: {response.text}")
        exit(1)
except Exception as e:
    print(f"Exception: {e}")
    exit(1)

# 2. Get estoque with token
print("\n=== STEP 2: GET /estoque ===")
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
print(f"Headers: {headers}")

try:
    response = requests.get(
        f"{base_url}/estoque",
        headers=headers,
        verify=False,
        timeout=60,
    )
    print(f"Status: {response.status_code}")
    print(f"Content-Length: {len(response.content)}")
    
    if response.status_code == 200:
        dados = response.json()
        if isinstance(dados, list):
            print(f"✅ Estoque: {len(dados)} registros")
            if dados:
                print(f"First record: {dados[0]}")
        else:
            print(f"Response type: {type(dados)}")
            print(f"Response: {dados}")
    else:
        print(f"Error: {response.status_code} - {response.text[:500]}")
        
except Exception as e:
    print(f"❌ Exception: {e}")
    import traceback
    traceback.print_exc()
