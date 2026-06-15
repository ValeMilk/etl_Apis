import calendar
import logging
import time
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
        token_refresh_hours: int = 12,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.token_refresh_hours = token_refresh_hours
        self.logger = logging.getLogger(self.__class__.__name__)
        self._token: Optional[str] = None
        self._token_obtained_at: Optional[datetime] = None

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
                token = response.text.strip()
                self._token_obtained_at = datetime.now()
                self.logger.info("Token obtained successfully, valid for ~%dh", self.token_refresh_hours)
                return token
            self.logger.error("Login failed: %s", response.status_code)
        except Exception:
            self.logger.exception("Login request failed")
        return None

    def _is_token_expired(self) -> bool:
        """Verifica se o token precisa ser renovado (token Cometa expira diariamente)."""
        if not self._token or not self._token_obtained_at:
            return True
        elapsed = datetime.now() - self._token_obtained_at
        return elapsed >= timedelta(hours=self.token_refresh_hours)

    def _force_refresh_token(self) -> None:
        """Força renovação do token (chamado após 401)."""
        self.logger.warning("Forcing token refresh")
        self._token = None
        self._token_obtained_at = None
        self._token = self._obter_token()

    def _get_headers(self) -> Optional[dict]:
        """Retorna headers com autenticação, renovando token se expirado."""
        if self._is_token_expired():
            self.logger.info("Token expired or missing, refreshing...")
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
        - Retry automático até 10 vezes com backoff exponencial
        """
        headers = self._get_headers()
        if not headers:
            return []

        # Retry logic: tenta até 10 vezes com backoff exponencial
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
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
                    
                    # Desplanicar/padronizar dados - SUCESSO!
                    return flatten_estoque(estoque_list)
                
                elif response.status_code == 401:
                    self.logger.warning("Estoque request got 401, refreshing token and retrying")
                    self._force_refresh_token()
                    headers = self._get_headers()
                    if headers:
                        retry = requests.get(
                            f"{self.base_url}/estoque",
                            headers=headers,
                            verify=self.verify_ssl,
                            timeout=self.timeout,
                        )
                        if retry.status_code == 200:
                            dados = retry.json()
                            if isinstance(dados, list):
                                return flatten_estoque(dados)
                    # Se falhou após refresh, continua para retry
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = min(2 ** retry_count, 30)
                        self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                        time.sleep(wait_time)
                else:
                    retry_count += 1
                    self.logger.warning(
                        "Estoque request failed: status_code=%s (tentativa %d/%d)",
                        response.status_code, retry_count, max_retries
                    )
                    if retry_count < max_retries:
                        wait_time = min(2 ** retry_count, 30)
                        self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                        time.sleep(wait_time)
                        
            except Exception as e:
                retry_count += 1
                self.logger.warning(
                    "Estoque request failed (tentativa %d/%d): %s",
                    retry_count, max_retries, str(e)
                )
                if retry_count < max_retries:
                    wait_time = min(2 ** retry_count, 30)
                    self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                    time.sleep(wait_time)
        
        self.logger.error(f"❌ Falha permanente ao buscar estoque após {max_retries} tentativas")
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

            # A API não aceita janelas que cruzam meses — limita ao último dia do mês atual
            ultimo_dia_mes = calendar.monthrange(data_atual.year, data_atual.month)[1]
            fim_mes = data_atual.replace(day=ultimo_dia_mes)
            if intervalo_fim > fim_mes:
                intervalo_fim = fim_mes

            params = {
                "loja": int(loja_id),
                "dataInicial": data_atual.strftime("%d-%m-%Y"),
                "dataFinal": intervalo_fim.strftime("%d-%m-%Y"),
            }

            # Retry logic: tenta até 10 vezes com backoff exponencial
            max_retries = 10
            retry_count = 0
            success = False
            
            while not success and retry_count < max_retries:
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
                        success = True  # Sucesso! Sai do loop
                    elif res.status_code == 401:
                        self.logger.warning(
                            "Vendas request for loja=%s got 401, refreshing token and retrying",
                            loja_id
                        )
                        self._force_refresh_token()
                        headers = self._get_headers()
                        if headers:
                            retry = requests.get(
                                url_venda,
                                headers=headers,
                                params=params,
                                verify=self.verify_ssl,
                                timeout=self.timeout,
                            )
                            if retry.status_code == 200:
                                dados = retry.json()
                                if isinstance(dados, (dict, list)):
                                    vendas_brutos.append(dados)
                                success = True
                    else:
                        self.logger.warning(
                            "Vendas request for loja=%s failed: status_code=%s (tentativa %d/%d)",
                            loja_id, res.status_code, retry_count + 1, max_retries
                        )
                        retry_count += 1
                        if retry_count < max_retries:
                            wait_time = min(2 ** retry_count, 30)
                            self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                            time.sleep(wait_time)
                except Exception as e:
                    retry_count += 1
                    self.logger.warning(
                        "Vendas request failed for loja=%s, period=%s-%s (tentativa %d/%d): %s",
                        loja_id, data_atual.date(), intervalo_fim.date(), retry_count, max_retries, str(e)
                    )
                    if retry_count < max_retries:
                        wait_time = min(2 ** retry_count, 30)
                        self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(
                            "❌ Falha permanente após %d tentativas para loja=%s período %s-%s",
                            max_retries, loja_id, data_atual.date(), intervalo_fim.date()
                        )

            data_atual = intervalo_fim + timedelta(days=1)

        # Sanitização: retorna lista vazia se nenhum dado foi coletado
        if not vendas_brutos:
            self.logger.debug("No vendas data collected for loja=%s", loja_id)
            return []
        
        # Desplanicar os dados antes de retornar
        return flatten_vendas(vendas_brutos)

    def get_vendas_periodo(self, data_inicio: datetime, data_fim: datetime) -> List[dict]:
        """
        Retorna vendas de TODAS as lojas em um período DESPLANIFICADAS.
        Não usa filtro de loja — a API retorna todas as lojas de uma vez.
        Respeita limite de 3 dias e limite de mês por janela.
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

            # Limita ao último dia do mês — API rejeita janelas que cruzam meses
            ultimo_dia_mes = calendar.monthrange(data_atual.year, data_atual.month)[1]
            fim_mes = data_atual.replace(day=ultimo_dia_mes)
            if intervalo_fim > fim_mes:
                intervalo_fim = fim_mes

            params = {
                "dataInicial": data_atual.strftime("%d-%m-%Y"),
                "dataFinal": intervalo_fim.strftime("%d-%m-%Y"),
            }

            # Retry logic: tenta até 10 vezes com backoff exponencial
            max_retries = 10
            retry_count = 0
            success = False
            
            while not success and retry_count < max_retries:
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
                        if isinstance(dados, list) and dados:
                            vendas_brutos.extend(dados)  # Cada elemento é uma loja
                        elif isinstance(dados, dict) and dados:
                            vendas_brutos.append(dados)
                        success = True  # Sucesso! Sai do loop
                    elif res.status_code == 401:
                        self._force_refresh_token()
                        headers = self._get_headers()
                        if headers:
                            retry = requests.get(
                                url_venda,
                                headers=headers,
                                params=params,
                                verify=self.verify_ssl,
                                timeout=self.timeout,
                            )
                            if retry.status_code == 200:
                                dados = retry.json()
                                if isinstance(dados, list) and dados:
                                    vendas_brutos.extend(dados)
                                elif isinstance(dados, dict) and dados:
                                    vendas_brutos.append(dados)
                                success = True
                    else:
                        self.logger.warning(
                            "Vendas periodo request failed: status_code=%s period=%s-%s (tentativa %d/%d)",
                            res.status_code, data_atual.date(), intervalo_fim.date(), retry_count + 1, max_retries
                        )
                        retry_count += 1
                        if retry_count < max_retries:
                            wait_time = min(2 ** retry_count, 30)  # Backoff exponencial, max 30s
                            self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                            time.sleep(wait_time)
                except Exception as e:
                    retry_count += 1
                    self.logger.warning(
                        "Vendas periodo request failed for period %s-%s (tentativa %d/%d): %s",
                        data_atual.date(), intervalo_fim.date(), retry_count, max_retries, str(e)
                    )
                    if retry_count < max_retries:
                        wait_time = min(2 ** retry_count, 30)  # Backoff exponencial, max 30s
                        self.logger.info(f"⏳ Aguardando {wait_time}s antes de tentar novamente...")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(
                            "❌ Falha permanente após %d tentativas para período %s-%s",
                            max_retries, data_atual.date(), intervalo_fim.date()
                        )

            data_atual = intervalo_fim + timedelta(days=1)

        if not vendas_brutos:
            return []

        return flatten_vendas(vendas_brutos)