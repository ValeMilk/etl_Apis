import logging
from datetime import datetime, timedelta
from typing import List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CometaClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        password: str,
        timeout: int = 30,
        verify_ssl: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.logger = logging.getLogger(self.__class__.__name__)
        self._token: Optional[str] = None

    def _obter_token(self) -> Optional[str]:
        url_login = f"{self.base_url}/login"
        payload = {"email": self.email, "password": self.password}
        try:
            response = requests.post(
                url_login,
                json=payload,
                headers={"Content-Type": "application/json"},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return response.text.strip()
            self.logger.error("Login failed: %s", response.status_code)
        except Exception:
            self.logger.exception("Login request failed")
        return None

    def _get_headers(self) -> Optional[dict]:
        if not self._token:
            self._token = self._obter_token()
        if not self._token:
            return None
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def get_estoque(self) -> List[dict]:
        headers = self._get_headers()
        if not headers:
            return []

        try:
            response = requests.get(
                f"{self.base_url}/estoque",
                headers=headers,
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                dados = response.json()
                if isinstance(dados, list):
                    return dados
                if isinstance(dados, dict) and "ESTOQUE" in dados:
                    return dados["ESTOQUE"]
            self.logger.error("Estoque request failed: %s", response.status_code)
        except Exception:
            self.logger.exception("Estoque request failed")
        return []

    def list_lojas(self) -> List[int]:
        estoque = self.get_estoque()
        lojas = set()
        for item in estoque:
            for key in ("LOJA", "loja", "ID_LOJA", "id_loja"):
                if key in item and item[key] is not None:
                    try:
                        lojas.add(int(item[key]))
                    except (TypeError, ValueError):
                        continue
        return sorted(lojas)

    def get_vendas_loja(self, loja_id: int, data_inicio: datetime, data_fim: datetime) -> List[dict]:
        headers = self._get_headers()
        if not headers:
            return []

        url_venda = f"{self.base_url}/venda"
        linhas: List[dict] = []
        data_atual = data_inicio

        while data_atual <= data_fim:
            intervalo_fim = data_atual + timedelta(days=2)
            if intervalo_fim > data_fim:
                intervalo_fim = data_fim

            params = {
                "loja": int(loja_id),
                "dataInicial": data_atual.strftime("%d-%m-%Y"),
                "dataFinal": intervalo_fim.strftime("%d-%m-%Y"),
            }

            try:
                res = requests.get(
                    url_venda,
                    headers=headers,
                    params=params,
                    verify=self.verify_ssl,
                    timeout=self.timeout,
                )
                if res.status_code == 200:
                    dados = res.json()

                    info_loja = dados.get("LOJA", {}) if isinstance(dados, dict) else {}
                    lista_vendas = (
                        dados.get("VENDAS", [])
                        if isinstance(dados, dict)
                        else (dados if isinstance(dados, list) else [])
                    )

                    for venda in lista_vendas:
                        linha = {
                            "ID_LOJA": info_loja.get("LOJA", loja_id),
                            "NOME_LOJA": info_loja.get("NOME", ""),
                            "CNPJ_LOJA": info_loja.get("CNPJ", ""),
                        }
                        linha.update(venda)
                        linhas.append(linha)
                else:
                    self.logger.error("Vendas request failed for loja %s: %s", loja_id, res.status_code)
            except Exception:
                self.logger.exception("Vendas request failed for loja %s", loja_id)

            data_atual = intervalo_fim + timedelta(days=1)

        return linhas