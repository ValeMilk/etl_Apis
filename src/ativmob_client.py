"""
Client para API ATIVMOB (api5.ativmob.com.br).

Gerencia eventos de estoque com sistema de ACK para evitar duplicação.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class AtivmobClient:
    """
    Client para API ATIVMOB v2.
    
    Fluxo:
    1. GET /get_events/ → retorna eventos novos
    2. Processar eventos localmente
    3. POST /ack_events/ → marca eventos como lidos (não retornam mais)
    """

    BASE_URL = "https://api5.ativmob.com.br/v2/orders/delivery"

    def __init__(self, api_key: str, store_cnpj: str, timeout: int = 30) -> None:
        """
        Args:
            api_key: X-API-Key para autenticação
            store_cnpj: CNPJ da loja (ex: 02518353000294)
            timeout: Timeout em segundos para requisições
        """
        self.api_key = api_key
        self.store_cnpj = store_cnpj
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers padrão com autenticação."""
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ── Obter eventos ─────────────────────────────────────────────────────────

    def get_events(self, event_code: str = "estoque") -> Dict:
        """
        Busca eventos novos da API.
        
        API só retorna eventos ainda não confirmados via ACK.
        
        Args:
            event_code: Código do evento (padrão: "estoque")
            
        Returns:
            {
                "maxNumEvents": 100,
                "startDateTime": "2026-05-20 12:12:29",
                "events": [...]
            }
        """
        url = f"{self.BASE_URL}/get_events/"
        params = {
            "storeCNPJ": self.store_cnpj,
            "event_code": event_code,
        }

        self.logger.info("Buscando eventos ATIVMOB: storeCNPJ=%s event_code=%s", self.store_cnpj, event_code)

        try:
            resp = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()

            events = data.get("events", [])
            self.logger.info("✅ ATIVMOB retornou %d eventos", len(events))
            return data

        except requests.exceptions.RequestException as e:
            self.logger.error("❌ Erro ao buscar eventos ATIVMOB: %s", e, exc_info=True)
            raise

    # ── ACK (confirmar eventos processados) ───────────────────────────────────

    def ack_events(self, event_ids: List[str]) -> bool:
        """
        Confirma que eventos foram processados (ACK).
        
        Após o ACK, esses eventos não retornam mais em get_events().
        
        Args:
            event_ids: Lista de IDs de eventos processados (ex: ["283007", "283008"])
            
        Returns:
            True se ACK bem-sucedido
        """
        if not event_ids:
            self.logger.warning("⚠️ Nenhum event_id para fazer ACK")
            return False

        url = f"{self.BASE_URL}/ack_events/"
        payload = {
            "storeCNPJ": self.store_cnpj,
            "events_ids": event_ids,
        }

        self.logger.info("Enviando ACK para %d eventos: %s", len(event_ids), event_ids[:5])

        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout,
                verify=False,
            )
            resp.raise_for_status()

            self.logger.info("✅ ACK enviado com sucesso para %d eventos", len(event_ids))
            return True

        except requests.exceptions.RequestException as e:
            self.logger.error("❌ Erro ao enviar ACK: %s", e, exc_info=True)
            return False
