#!/bin/bash
# docker/entrypoint-etl.sh
# Entry point do container ETL com bootstrap automático

set -e

echo "=========================================="
echo "BI_COMETA ETL Container Starting"
echo "=========================================="
echo ""

# Wait for database to be ready (90 seconds timeout)
echo "Waiting for database to be ready..."

python3 << 'WAIT_DB'
import sys
import time
import os
from sqlalchemy import create_engine, text

db_url = os.environ.get('DB_URL')
if not db_url:
    db_url = 'postgresql+psycopg2://bi_user:bi_password@db:5432/bi_cometa'

max_attempts = 90
attempt = 0

while attempt < max_attempts:
    try:
        engine = create_engine(db_url, connect_args={"connect_timeout": 10})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database is ready", flush=True)
        sys.exit(0)
    except Exception as e:
        attempt += 1
        if attempt < max_attempts:
            print(f"⏳ Waiting for database... ({attempt}/{max_attempts})", flush=True)
            time.sleep(1)
        else:
            print(f"❌ Database failed to start after {max_attempts} seconds", flush=True)
            sys.exit(1)

WAIT_DB

# Check if bootstrap is needed
echo "Checking if bootstrap is needed..."

BOOTSTRAP_NEEDED=$(python3 << 'CHECK_BOOTSTRAP'
import sys
import os
from sqlalchemy import create_engine, text

try:
    db_url = os.environ.get('DB_URL', 'postgresql://bi_user:bi_password@db:5432/bi_cometa')
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Check if vendas table exists
        result = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name='vendas' LIMIT 1")
        ).fetchone()
        
        if not result:
            print("1")  # Bootstrap needed
            sys.exit(0)
        
        # Count vendas
        count = conn.execute(text("SELECT COUNT(*) FROM vendas")).scalar() or 0
        
        if count == 0:
            print("1")  # Bootstrap needed
        else:
            print("0")  # Bootstrap not needed
            
except Exception as e:
    print("1")  # On error, assume bootstrap needed
    
sys.exit(0)

CHECK_BOOTSTRAP
)

if [ "$BOOTSTRAP_NEEDED" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "🔄 BOOTSTRAP: Initializing database"
    echo "=========================================="
    echo ""
    
    cd /app
    
    python3 << 'BOOTSTRAP_SCRIPT'
import sys
sys.path.insert(0, '/app')

try:
    from bootstrap import Bootstrap
    
    bootstrap = Bootstrap()
    success = bootstrap.run()
    
    sys.exit(0 if success else 1)

except Exception as e:
    import logging
    logging.error(f"❌ BOOTSTRAP FAILED: {e}", exc_info=True)
    sys.exit(1)

BOOTSTRAP_SCRIPT

    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ Bootstrap failed!"
        echo "Container will exit."
        exit 1
    fi
else
    echo "✅ Database already initialized, skipping bootstrap"
fi

echo ""
echo "=========================================="
echo "🚀 Starting ETL Scheduler"
echo "=========================================="
echo ""

# Run ETL worker
cd /app
exec python3 etl_worker.py
