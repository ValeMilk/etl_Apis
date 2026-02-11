import logging
from datetime import datetime, timedelta
from typing import List, Optional

import requests
import urllib3

from App.shared.utils import flatten_vendas, flatten_estoque

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CometaClient:
    """
    Cliente para consumir dados da API Cometa.
    Realiza autenticação, extração de estoque e vendas.
    """

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
        """Autentica na API e retorna o token."""
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
        """Retorna headers com autenticação, fazendo login se necessário."""
        if not self._token:
            self._token = self._obter_token()
        if not self._token:
            return None
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def get_estoque(self) -> List[dict]:
        """
        Retorna estoque atual DESPLANIFICADO.
        Cada linha é um produto em uma loja.
        
        Sanitização:
        - Valida resposta da API
        - Extrai estrutura de estoque (se aninhada em dict)
        - Retorna lista vazia se erro ou formato inválido
        """
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
                
                # Sanitização: validação básica de resposta
                if dados is None:
                    self.logger.warning("Estoque response is None, returning empty list")
                    return []
                
                # Extração de estrutura (se aninhada)
                estoque_list: List[dict] = []
                if isinstance(dados, list):
                    estoque_list = dados
                elif isinstance(dados, dict):
                    # Tenta chaves comuns
                    for key in ("ESTOQUE", "estoque", "data", "DATA", "items", "ITEMS"):
                        if key in dados and isinstance(dados[key], list):
                            estoque_list = dados[key]
                            break
                    
                    if not estoque_list:
                        self.logger.warning(
                            "Estoque response is dict without expected list key. Keys: %s",
                            list(dados.keys())[:10]
                        )
                        return []
                else:
                    self.logger.warning(
                        "Estoque response has unexpected type: %s. Expected list or dict",
                        type(dados).__name__
                    )
                    return []
                
                # Desplanicar/padronizar dados
                return flatten_estoque(estoque_list)
            
            self.logger.error("Estoque request failed: status_code=%s", response.status_code)
        except Exception:
            self.logger.exception("Estoque request failed")
        
        return []

    def list_lojas(self) -> List[int]:
        """Retorna lista de IDs de lojas a partir do estoque."""
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
        """
        Retorna vendas da loja DESPLANIFICADAS.
        Cada linha é uma venda individual (produto + quantidade + valor).
        
        Sanitização:
        - Valida resposta da API antes de processar
        - Retorna lista vazia se erro ou formato inválido
        - Permite que parcial de dados seja processado
        """
        headers = self._get_headers()
        if not headers:
            return []

        url_venda = f"{self.base_url}/venda"
        vendas_brutos: List[dict] = []
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
                    
                    # Sanitização: validação básica antes de adicionar
                    if dados is None:
                        self.logger.debug(
                            "Vendas response for loja=%s, period=%s-%s is None, skipping",
                            loja_id, data_atual.date(), intervalo_fim.date()
                        )
                    elif isinstance(dados, (dict, list)):
                        vendas_brutos.append(dados)
                    else:
                        self.logger.warning(
                            "Vendas response for loja=%s has unexpected type: %s. Expected dict or list",
                            loja_id, type(dados).__name__
                        )
                else:
                    self.logger.warning(
                        "Vendas request for loja=%s failed: status_code=%s",
                        loja_id, res.status_code
                    )
            except Exception:
                self.logger.exception(
                    "Vendas request failed for loja=%s, period=%s-%s",
                    loja_id, data_atual.date(), intervalo_fim.date()
                )

            data_atual = intervalo_fim + timedelta(days=1)

        # Sanitização: retorna lista vazia se nenhum dado foi coletado
        if not vendas_brutos:
            self.logger.debug("No vendas data collected for loja=%s", loja_id)
            return []
        
        # Desplanicar os dados antes de retornar
        return flatten_vendas(vendas_brutos)