"""
Debug: Verificar por que leaflet específico 6a4bd30be4641dffe856867d não está no banco.
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
logger = logging.getLogger("CheckLeaflet")


def main():
    leaflet_id = "6a4bd30be4641dffe856867d"
    periodo_str = "02/07 a 08/07"
    
    logger.info("=" * 80)
    logger.info(f"DEBUG: Leaflet {leaflet_id} ({periodo_str})")
    logger.info("=" * 80)
    
    # 1. Verificar se está no banco
    logger.info("\n💾 Step 1: Verificando se leaflet está no banco...")
    
    db_client = DatabaseClient(db_url=settings.db_url, echo=False)
    
    query_count = text("""
        SELECT COUNT(*) as total
        FROM public.infomarket 
        WHERE leaflet_id = :leaflet_id
    """)
    
    with db_client.engine.connect() as conn:
        result = conn.execute(query_count, {"leaflet_id": leaflet_id}).fetchone()
        total = result[0] if result else 0
    
    if total > 0:
        logger.info(f"✅ Leaflet ENCONTRADO no banco: {total} registros")
        
        query_details = text("""
            SELECT 
                leaflet_name,
                network_name,
                validity_start_date,
                validity_finish_date,
                COUNT(*) as items,
                MIN(created_at) as first_insert,
                MAX(created_at) as last_insert
            FROM public.infomarket
            WHERE leaflet_id = :leaflet_id
            GROUP BY leaflet_name, network_name, validity_start_date, validity_finish_date
        """)
        
        with db_client.engine.connect() as conn:
            details = conn.execute(query_details, {"leaflet_id": leaflet_id}).fetchone()
            
            logger.info(f"  - leaflet_name: {details[0]}")
            logger.info(f"  - network_name: {details[1]}")
            logger.info(f"  - validity_start_date: {details[2]}")
            logger.info(f"  - validity_finish_date: {details[3]}")
            logger.info(f"  - items: {details[4]}")
            logger.info(f"  - first_insert: {details[5]}")
            logger.info(f"  - last_insert: {details[6]}")
        
        logger.info("\n✅ Leaflet JÁ ESTÁ NO BANCO! Não há problema.")
        return 0
    
    logger.info(f"⚠️ Leaflet NÃO encontrado no banco!")
    
    # 2. Buscar na API no período 02/07 a 08/07
    logger.info("\n📡 Step 2: Buscando leaflet na API (02/07 → 08/07)...")
    
    client = InfomarketClient(
        email=settings.infomarket_email,
        password=settings.infomarket_password.get_secret_value(),
        timeout=60
    )
    
    start = datetime(2026, 7, 2)
    finish = datetime(2026, 7, 8)
    
    records = client.get_prices(start, finish)
    logger.info(f"✅ API retornou: {len(records)} registros totais no período")
    
    # 3. Filtrar pelo leaflet_id específico
    target_records = [r for r in records if r.get("leaflet_id") == leaflet_id]
    
    if target_records:
        logger.info(f"✅ Leaflet ENCONTRADO na API: {len(target_records)} registros")
        
        first = target_records[0]
        logger.info("\n📋 Dados do primeiro registro:")
        logger.info(f"  - leaflet_id: {first.get('leaflet_id')}")
        logger.info(f"  - leaflet_name: {first.get('leaflet_name')}")
        logger.info(f"  - network_name: {first.get('network_name')}")
        logger.info(f"  - network_id: {first.get('network_id')}")
        logger.info(f"  - brand_name: {first.get('brand_name')}")
        logger.info(f"  - validity_start_date: {first.get('validity_start_date')}")
        logger.info(f"  - validity_finish_date: {first.get('validity_finish_date')}")
        logger.info(f"  - store_name: {first.get('store_name')}")
        logger.info(f"  - value: {first.get('value')}")
        logger.info(f"  - price_id: {first.get('price_id')}")
        
        # 4. Tentar inserir no banco
        logger.info(f"\n⚡ Step 3: Inserindo {len(target_records)} registros no banco...")
        
        rows, date_range = db_client._prepare_infomarket_rows(target_records)
        logger.info(f"✅ Rows preparadas: {len(rows)}")
        logger.info(f"✅ Date range: {date_range[0]} → {date_range[1]}")
        
        if len(rows) != len(target_records):
            logger.warning(f"⚠️ ATENÇÃO: {len(target_records)} registros API → {len(rows)} rows preparadas")
            logger.warning("Alguns registros foram filtrados durante prepare!")
            
            # Investigar o que foi filtrado
            for rec in target_records[:5]:
                price_id = rec.get("price_id")
                if not price_id:
                    logger.error(f"❌ Registro SEM price_id: {rec}")
        
        from sqlalchemy import insert
        
        with db_client.get_session() as session:
            session.execute(insert(db_client.infomarket), rows)
            inserted = len(rows)
        
        logger.info(f"✅ Inseridos {inserted} registros!")
        
        # 5. Verificar se agora está no banco
        with db_client.engine.connect() as conn:
            result = conn.execute(query_count, {"leaflet_id": leaflet_id}).fetchone()
            total_after = result[0] if result else 0
        
        logger.info(f"✅ Verificação final: {total_after} registros do leaflet no banco")
        
    else:
        logger.error(f"❌ Leaflet NÃO ENCONTRADO na API!")
        logger.info("\n📊 Analisando o que veio da API...")
        
        # Mostrar leaflets do COMETA no período
        cometa_records = [r for r in records if r.get("network_name") == "COMETA"]
        logger.info(f"Registros COMETA no período: {len(cometa_records)}")
        
        if cometa_records:
            leaflets = {}
            for r in cometa_records:
                lid = r.get("leaflet_id")
                if lid not in leaflets:
                    leaflets[lid] = {
                        "name": r.get("leaflet_name"),
                        "start": r.get("validity_start_date"),
                        "finish": r.get("validity_finish_date"),
                        "count": 0
                    }
                leaflets[lid]["count"] += 1
            
            logger.info(f"\nLeaflets COMETA encontrados ({len(leaflets)}):")
            for lid, info in list(leaflets.items())[:10]:
                logger.info(f"  - {lid[:20]}... | {info['name'][:30]} | {info['start']}→{info['finish']} | {info['count']} itens")
        else:
            logger.warning("⚠️ NENHUM registro do COMETA encontrado no período!")
    
    logger.info("\n" + "=" * 80)
    logger.info("DEBUG CONCLUÍDO")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Erro durante debug")
        sys.exit(1)
