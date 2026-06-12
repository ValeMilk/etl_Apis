"""
Client para API InfoMarket Pesquisa (app.infomarketpesquisa.com).

Gerencia autenticação com token de 14 dias e paginação automática.
"""
import logging
from datetime import datetime
from typing import List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class InfomarketClient:
    """
    Client para API InfoMarket Pesquisa.

    - Login via POST /api/users/login (email/password como headers)
    - Token válido por 14 dias — auto-refresh 1 dia antes de expirar
    - Paginação automática via limit/skip em /api/leaflets/getPrices
    """

    BASE_URL = "https://app.infomarketpesquisa.com"
    TOKEN_TTL_DAYS = 14
    PAGE_SIZE = 1000

    def __init__(self, email: str, password: str, timeout: int = 30) -> None:
        self.email = email
        self.password = password
        self.timeout = max(timeout, 120)  # mínimo 120s para suportar janelas grandes
        self.logger = logging.getLogger(self.__class__.__name__)

        self._token: Optional[str] = None
        self._token_obtained_at: Optional[datetime] = None

    # ── Token management ─────────────────────────────────────────────────────

    def _is_token_valid(self) -> bool:
        if not self._token or not self._token_obtained_at:
            return False
        age_days = (datetime.utcnow() - self._token_obtained_at).total_seconds() / 86400
        return age_days < (self.TOKEN_TTL_DAYS - 1)  # Renova 1 dia antes

    def _obtain_token(self) -> str:
        """Faz login e armazena token."""
        url = f"{self.BASE_URL}/api/users/login"
        resp = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "email": self.email,
                "password": self.password,
            },
            timeout=self.timeout,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()

        token = (
            data.get("accessToken")
            or data.get("token")
            or data.get("access_token")
            or data.get("id")  # InfoMarket retorna o token no campo "id"
        )
        if not token:
            raise ValueError(f"Token não encontrado na resposta de login. Campos: {list(data.keys())}")

        self._token = token
        self._token_obtained_at = datetime.utcnow()
        self.logger.info("InfoMarket token obtido com sucesso (~14 dias de validade)")
        return token

    def _get_token(self) -> str:
        if not self._is_token_valid():
            self.logger.info("InfoMarket token ausente ou expirado, renovando...")
            return self._obtain_token()
        return self._token  # type: ignore[return-value]

    # ── Data fetching ─────────────────────────────────────────────────────────

    def get_prices(self, start_date: datetime, finish_date: datetime) -> List[dict]:
        """
        Busca preços/encartes no intervalo de datas com paginação automática.

        Args:
            start_date:   Data de início (validity_start_date)
            finish_date:  Data de fim (validity_finish_date)

        Returns:
            Lista completa de registros de preços (todas as páginas)
        """
        token = self._get_token()
        start_str = start_date.strftime("%Y%m%d")
        finish_str = finish_date.strftime("%Y%m%d")
        url = f"{self.BASE_URL}/api/leaflets/getPrices"

        all_records: List[dict] = []
        skip = 0

        while True:
            params = {
                "startDate": start_str,
                "finishDate": finish_str,
                "limit": self.PAGE_SIZE,
                "skip": skip,
                "accessToken": token,
            }

            resp = requests.get(url, params=params, timeout=self.timeout, verify=False)

            # Retry once on 401 (token expirado no servidor antes do prazo local)
            if resp.status_code == 401:
                self.logger.warning("InfoMarket 401 — token expirado no servidor, renovando...")
                token = self._obtain_token()
                params["accessToken"] = token
                resp = requests.get(url, params=params, timeout=self.timeout, verify=False)

            resp.raise_for_status()
            data = resp.json()

            records: List[dict] = (
                data if isinstance(data, list)
                else data.get("data", data.get("results", []))
            )

            if not records:
                break

            all_records.extend(records)
            self.logger.debug("InfoMarket skip=%d → %d registros nesta página", skip, len(records))

            if len(records) < self.PAGE_SIZE:
                break

            skip += self.PAGE_SIZE

        self.logger.info(
            "InfoMarket getPrices %s→%s: %d registros total",
            start_str, finish_str, len(all_records)
        )
        return all_records
