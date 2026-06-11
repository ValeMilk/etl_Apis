============================================
VERIFICAR QUANTAS VENDAS TEM NO BANCO AGORA
(rode primeiro antes de qualquer coisa)
============================================

docker exec -it bi_cometa_db psql -U bi_user -d bi_cometa -c "SELECT COUNT(*), MIN(data), MAX(data) FROM vendas;"


============================================
PASSO 1 - ENVIAR CÓDIGO (PowerShell LOCAL)
============================================

cd "C:\Users\LENOVO 059\Desktop\ETL API\BI_COMETA"
scp src/api_cometa.py root@72.61.62.17:/home/jefferson_pwr/BI_COMETA/src/api_cometa.py
scp "src/App/etl/etl_service.py" root@72.61.62.17:/home/jefferson_pwr/BI_COMETA/src/App/etl/etl_service.py


============================================
PASSO 2 - REBUILD + RECRIAR CONTAINER (no VPS)
(docker start não usa a nova imagem - precisa recriar)
============================================

cd /home/jefferson_pwr/BI_COMETA
docker-compose -f docker/docker-compose.yml stop etl
docker-compose -f docker/docker-compose.yml build --no-cache etl
docker-compose -f docker/docker-compose.yml up -d etl


============================================
PASSO 3 - VER LOGS
============================================

docker logs bi_cometa_etl -f --tail 30
