import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Desativa avisos de segurança SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAÇÕES DE ACESSO ---
BASE_URL = "https://vendas.cometasupermercados.com.br"
EMAIL = "comercial@valemilk.com.br"
PASSWORD = "@valemilk"

def obter_token():
    url_login = f"{BASE_URL}/login"
    payload = {"email": EMAIL, "password": PASSWORD}
    try:
        response = requests.post(url_login, json=payload, headers={"Content-Type": "application/json"}, verify=False, timeout=20)
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        print(f"Erro na autenticação: {e}")
    return None

def processar_estoque(headers):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Extraindo estoque atual...")
    try:
        response = requests.get(f"{BASE_URL}/estoque", headers=headers, verify=False, timeout=60)
        if response.status_code == 200:
            dados = response.json()
            df_estq = pd.DataFrame(dados)
            # Padroniza colunas do estoque para maiúsculo
            df_estq.columns = [c.upper() for c in df_estq.columns]
            df_estq.to_csv("estoque_atual.csv", index=False, sep=";", encoding="utf-8-sig")
            
            # O campo de loja no estoque geralmente é 'loja' ou 'LOJA'
            col_loja = 'LOJA' if 'LOJA' in df_estq.columns else df_estq.columns[0]
            lojas = sorted(df_estq[col_loja].unique().tolist())
            print(f"✅ Arquivo 'estoque_atual.csv' gerado ({len(lojas)} lojas).")
            return lojas
    except Exception as e:
        print(f"❌ Falha ao processar estoque: {e}")
    return []

def buscar_vendas_por_loja(loja_id, headers, data_inicio, data_fim):
    url_venda = f"{BASE_URL}/venda"
    linhas_planificadas = []
    data_atual = data_inicio
    
    while data_atual <= data_fim:
        intervalo_fim = data_atual + timedelta(days=2)
        if intervalo_fim > data_fim: intervalo_fim = data_fim
        
        params = {
            "loja": int(loja_id),
            "dataInicial": data_atual.strftime("%d-%m-%Y"),
            "dataFinal": intervalo_fim.strftime("%d-%m-%Y")
        }
        
        try:
            res = requests.get(url_venda, headers=headers, params=params, verify=False, timeout=30)
            if res.status_code == 200:
                dados = res.json()
                
                # Extração segura de dados da loja e lista de vendas
                info_loja = dados.get("LOJA", {}) if isinstance(dados, dict) else {}
                lista_vendas = dados.get("VENDAS", []) if isinstance(dados, dict) else (dados if isinstance(dados, list) else [])
                
                for venda in lista_vendas:
                    # Cria a linha base com dados da loja
                    linha = {
                        "ID_LOJA": info_loja.get("LOJA", loja_id),
                        "NOME_LOJA": info_loja.get("NOME", ""),
                        "CNPJ_LOJA": info_loja.get("CNPJ", "")
                    }
                    # Adiciona os dados da venda (Garante que as chaves fiquem em maiúsculo depois)
                    linha.update(venda)
                    linhas_planificadas.append(linha)
        except:
            pass
        
        data_atual = intervalo_fim + timedelta(days=1)
    
    return linhas_planificadas

def executar_automacao():
    token = obter_token()
    if not token: 
        print("Erro: Token não obtido.")
        return

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    lojas = processar_estoque(headers)
    
    if not lojas: return

    hoje = datetime.now()
    inicio_mes = hoje.replace(day=1)
    todas_vendas = []

    print(f"\nIniciando extração de vendas (Paralelo)...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futuros = {executor.submit(buscar_vendas_por_loja, l, headers, inicio_mes, hoje): l for l in lojas}
        for f in as_completed(futuros):
            res_loja = f.result()
            todas_vendas.extend(res_loja)
            print(f"   Loja {futuros[f]:02d}: {len(res_loja)} registros.")

    if todas_vendas:
        df_vendas = pd.DataFrame(todas_vendas)
        
        # 1. Padroniza todos os nomes de colunas para MAIÚSCULO
        df_vendas.columns = [c.upper() for c in df_vendas.columns]
        
        # 2. Define a ordem de preferência (apenas colunas que existem)
        ordem_pref = ['ID_LOJA', 'NOME_LOJA', 'CNPJ_LOJA', 'DATA', 'PRODUTO', 'QTD', 'VENDA', 'CUSTO', 'EAN', 'COD_INTERNO']
        
        # Filtra apenas as que realmente existem no DataFrame para evitar KeyError
        cols_final = [c for c in ordem_pref if c in df_vendas.columns]
        
        # Adiciona quaisquer outras colunas extras que sobraram
        extras = [c for c in df_vendas.columns if c not in cols_final]
        
        # Aplica a reorganização segura
        df_vendas = df_vendas[cols_final + extras]
        
        # Salva o arquivo final
        df_vendas.to_csv("vendas_mes_atual.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"\n🚀 PROCESSO CONCLUÍDO!")
        print(f"📍 Vendas salvas: 'vendas_mes_atual.csv' ({len(df_vendas)} linhas)")
    else:
        print("\n⚠️ Nenhuma venda encontrada.")

if __name__ == "__main__":
    executar_automacao()