#!/usr/bin/env python3
"""
Bootstrap completo de Vendas: apaga e repuxa TODOS os dados de ValeMilk e ValeFish
desde o período disponível até ontem.
"""

import logging
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
)
logger = logging.getLogger("BootstrapVendas")

from api_cometa import CometaClient
from App.core.config import settings
from App.core.database import DatabaseClient
from sqlalchemy import delete


def bootstrap_vendas(brand: str, cometa_client: CometaClient, db_client: DatabaseClient) -> None:
    """
    Bootstrap completo de vendas para uma marca:
    1. Deleta todos os registros existentes
    2. Repuxa desde 02/11/2022 até ontem
    3. Insere tudo no banco
    """
    logger.info("=" * 80)
    logger.info(f"BOOTSTRAP COMPLETO DE VENDAS [{brand.upper()}]")
    logger.info("=" * 80)
    
    try:
        # Determina qual tabela usar
        if brand.lower() == 'valemilk':
            table = db_client.vendas
            upsert_fn = db_client.upsert_vendas
        else:  # valefish
            table = db_client.vendas_valefish
            upsert_fn = db_client.upsert_vendas_valefish
        
        # Step 1: Deletar todos os registros existentes
        logger.info(f"[{brand}] Step 1: Deletando todos os registros de vendas...")
        with db_client.get_session() as session:
            delete_stmt = delete(table)
            result = session.execute(delete_stmt)
            deleted = result.rowcount or 0
        logger.info(f"[{brand}] Deletados {deleted} registros de vendas")
        
        # Step 2: Definir período de sincronização
        # Começando de 02/11/2022 (data fixa) até ontem
        hoje = datetime.now()
        fim = hoje - timedelta(days=1)  # API tem dados até ontem
        inicio = datetime(2022, 11, 2)  # Data fixa de início: 02/11/2022
        
        logger.info(f"[{brand}] Step 2: Puxando vendas de {inicio.date()} até {fim.date()} (~{(fim - inicio).days} dias)")
        
        # Step 3: Puxar dados por período (chunks de 60 dias para evitar timeout e acelerar)
        todas_vendas = []
        current_start = inicio
        chunk_size = 60  # dias
        
        while current_start < fim:
            current_end = min(current_start + timedelta(days=chunk_size), fim)
            logger.info(f"[{brand}] Fetching {current_start.date()} to {current_end.date()}...")
            
            try:
                # Tenta puxar sem filtro de loja primeiro
                vendas = cometa_client.get_vendas_periodo(current_start, current_end)
                todas_vendas.extend(vendas)
                logger.info(f"[{brand}]   → {len(vendas)} registros")
            except Exception as e:
                logger.warning(f"[{brand}] Erro ao puxar período {current_start.date()}-{current_end.date()}: {e}")
                # Se falhar, tenta por loja
                try:
                    lojas = cometa_client.list_lojas()
                    if lojas:
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            futuros = {
                                executor.submit(
                                    cometa_client.get_vendas_loja, loja, current_start, current_end
                                ): loja
                                for loja in lojas
                            }
                            for future in as_completed(futuros):
                                try:
                                    vendas = future.result()
                                    todas_vendas.extend(vendas)
                                except Exception as ex:
                                    logger.exception(f"[{brand}] Erro ao puxar loja {futuros[future]}: {ex}")
                except Exception as ex:
                    logger.exception(f"[{brand}] Erro ao listar lojas: {ex}")
            
            current_start = current_end + timedelta(days=1)
        
        # Step 4: Inserir todos os dados
        logger.info(f"[{brand}] Step 3: Inserindo {len(todas_vendas)} registros no banco...")
        if not todas_vendas:
            logger.warning(f"[{brand}] Nenhum registro foi puxado!")
            return
        
        deleted, inserted = upsert_fn(todas_vendas)
        logger.info(f"[{brand}] Resultado: Deleted={deleted}, Inserted={inserted}")
        
        logger.info(f"[{brand}] ✅ Bootstrap completo finalizado!")
        
    except Exception as e:
        logger.exception(f"[{brand}] ❌ Bootstrap falhou: {e}")
        raise


def main():
    """Entry point."""
    logger.info("Iniciando Bootstrap Completo de Vendas (ValeMilk + ValeFish)")
    
    try:
        # Inicializa DB
        db_client = DatabaseClient(db_url=settings.db_url, echo=False)
        
        # ── ValeMilk ──
        logger.info("\n" + "="*80)
        logger.info("INICIANDO BOOTSTRAP VALEMILK")
        logger.info("="*80)
        
        cometa_client_valemilk = CometaClient(
            base_url=settings.api_base_url,
            email=settings.api_email,
            password=settings.api_password.get_secret_value(),
            timeout=settings.request_timeout,
            verify_ssl=settings.verify_ssl,
            token_refresh_hours=settings.token_refresh_hours,
        )
        bootstrap_vendas('valemilk', cometa_client_valemilk, db_client)
        
        # ── ValeFish ──
        if settings.valefish_api_email:
            logger.info("\n" + "="*80)
            logger.info("INICIANDO BOOTSTRAP VALEFISH")
            logger.info("="*80)
            
            cometa_client_valefish = CometaClient(
                base_url=settings.api_base_url,
                email=settings.valefish_api_email,
                password=settings.valefish_api_password.get_secret_value(),
                timeout=settings.request_timeout,
                verify_ssl=settings.verify_ssl,
                token_refresh_hours=settings.token_refresh_hours,
            )
            bootstrap_vendas('valefish', cometa_client_valefish, db_client)
        else:
            logger.warning("Credenciais ValeFish não configuradas, pulando...")
        
        logger.info("\n" + "="*80)
        logger.info("✅ BOOTSTRAP COMPLETO FINALIZADO COM SUCESSO!")
        logger.info("="*80)
        
    except Exception:
        logger.exception("❌ Bootstrap falhou")
        sys.exit(1)


if __name__ == "__main__":
    main()
