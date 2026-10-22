"""
Debug: Verificar por que dados do COMETA (01/07-16/07) não estão sendo inseridos.
"""
import logging
import sys
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from App.core.config import settings
from App.core.database import DatabaseClient
from infomarket_client import InfomarketClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
)
logger = logging.getLogger("DebugCometa")


def main():
    logger.info("=" * 80)
    logger.info("DEBUG: COMETA 01/07 - 16/07")
    logger.info("=" * 80)
    
    # 1. Buscar dados da API para período 01/07 - 16/07
    logger.info("\n📡 Step 1: Buscando dados da API InfoMarket (01/07 → 16/07)...")
    
    client = InfomarketClient(
        email=settings.infomarket_email,
        password=settings.infomarket_password.get_secret_value(),
        timeout=60
    )
    
    start = datetime(2026, 7, 1)
    finish = datetime(2026, 7, 16)
    
    records = client.get_prices(start, finish)
    logger.info(f"✅ Total de registros retornados pela API: {len(records)}")
    
    # 2. Filtrar apenas COMETA
    cometa_records = [r for r in records if r.get("network_name") == "COMETA"]
    logger.info(f"✅ Registros do network COMETA: {len(cometa_records)}")
    
    if not cometa_records:
        logger.error("⚠️ PROBLEMA: API não retornou registros do COMETA!")
        logger.info("\nNetworks encontradas:")
        networks = {}
        for r in records:
            net = r.get("network_name", "NULL")
            networks[net] = networks.get(net, 0) + 1
        for net, count in sorted(networks.items(), key=lambda x: -x[1]):
            logger.info(f"  - {net}: {count} registros")
        return
    
    # 3. Mostrar sample de dados COMETA
    logger.info("\n📋 Sample de 3 registros COMETA:")
    for i, rec in enumerate(cometa_records[:3], 1):
        logger.info(f"\n  Registro {i}:")
        logger.info(f"    network_name: {rec.get('network_name')}")
        logger.info(f"    leaflet_id: {rec.get('leaflet_id')}")
        logger.info(f"    leaflet_name: {rec.get('leaflet_name')}")
        logger.info(f"    validity_start_date: {rec.get('validity_start_date')}")
        logger.info(f"    validity_finish_date: {rec.get('validity_finish_date')}")
        logger.info(f"    brand_name: {rec.get('brand_name')}")
        logger.info(f"    store_name: {rec.get('store_name')}")
        logger.info(f"    value: {rec.get('value')}")
    
    # 4. Preparar rows para inserção (mesmo código do database.py)
    logger.info("\n🔄 Step 2: Preparando dados para inserção no banco...")
    
    db_client = DatabaseClient(db_url=settings.db_url, echo=False)
    
    # Usar a mesma função que o script usa
    rows, date_range = db_client._prepare_infomarket_rows(cometa_records)
    logger.info(f"✅ Rows preparadas: {len(rows)}")
    logger.info(f"✅ Date range: {date_range[0]} → {date_range[1]}")
    
    # 5. Verificar se há algum filtro removendo dados
    if len(rows) != len(cometa_records):
        logger.warning(f"⚠️ ATENÇÃO: {len(cometa_records)} registros da API → {len(rows)} rows preparadas")
        logger.warning("Alguns registros foram filtrados durante o prepare!")
    
    # 6. Contar quantos registros COMETA existem no banco ANTES da inserção
    logger.info("\n💾 Step 3: Verificando registros COMETA no banco (ANTES)...")
    
    query_before = """
        SELECT COUNT(*) as total
        FROM public.infomarket
        WHERE network_name = 'COMETA'
          AND validity_start_date BETWEEN '2026-07-01' AND '2026-07-16'
    """
    
    with db_client.engine.connect() as conn:
        result = conn.execute(text(query_before)).fetchone()
        total_before = result[0] if result else 0
    
    logger.info(f"✅ Registros COMETA no banco (01/07-16/07): {total_before}")
    
    # 7. Simular inserção (replace_infomarket)
    logger.info("\n💾 Step 4: Simulando replace_infomarket...")
    logger.info(f"DELETE WHERE validity_start_date BETWEEN {date_range[0]} AND {date_range[1]}")
    logger.info(f"INSERT {len(rows)} rows")
    
    # 8. Verificar leaflet_ids únicos
    logger.info("\n📊 Step 5: Análise de leaflet_ids do COMETA:")
    
    leaflets = {}
    for rec in cometa_records:
        lid = rec.get("leaflet_id")
        if lid not in leaflets:
            leaflets[lid] = {
                "name": rec.get("leaflet_name"),
                "start": rec.get("validity_start_date"),
                "finish": rec.get("validity_finish_date"),
                "count": 0
            }
        leaflets[lid]["count"] += 1
    
    logger.info(f"✅ Total de encartes COMETA únicos: {len(leaflets)}")
    for lid, info in list(leaflets.items())[:5]:
        logger.info(f"  - {lid[:20]}... | {info['name'][:30]} | {info['start']}→{info['finish']} | {info['count']} itens")
    
    # 9. Executar inserção REAL
    logger.info("\n⚡ Step 6: EXECUTANDO replace_infomarket para COMETA...")
    deleted, inserted = db_client.replace_infomarket(cometa_records)
    logger.info(f"✅ Deleted: {deleted}, Inserted: {inserted}")
    
    # 10. Verificar registros COMETA DEPOIS da inserção
    logger.info("\n💾 Step 7: Verificando registros COMETA no banco (DEPOIS)...")
    
    with db_client.engine.connect() as conn:
        result = conn.execute(text(query_before)).fetchone()
        total_after = result[0] if result else 0
    
    logger.info(f"✅ Registros COMETA no banco (01/07-16/07): {total_after}")
    logger.info(f"📈 Diferença: {total_after - total_before:+d}")
    
    logger.info("\n" + "=" * 80)
    logger.info("DEBUG CONCLUÍDO")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Erro durante debug")
        sys.exit(1)
