import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from App.api.routes import create_router
from App.core.config import settings
from App.core.database import DatabaseClient

# Carrega variáveis de ambiente
load_dotenv()

# Configura logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
)
logger = logging.getLogger("API")

logger.info("BI_COMETA API Starting...")
logger.info("Configuration loaded and validated")

# Inicializa cliente de banco de dados
db_client = DatabaseClient(db_url=settings.db_url, echo=settings.database_echo)
logger.info("DatabaseClient initialized")

# Configura FastAPI
app = FastAPI(title=settings.app_title, version=settings.app_version)

# Middlewares de segurança
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)
logger.info("CORSMiddleware configured with origins: %s", settings.cors_origins)

app.add_middleware(GZipMiddleware, minimum_size=1000)
logger.info("GZipMiddleware configured (minimum_size=1000)") 

app.include_router(create_router(db_client))
logger.info("FastAPI app configured")


@app.get("/health")
def health_check() -> dict:
    """Health check para disponibilidade da API."""
    return {
        "status": "healthy",
        "service": "api",
        "version": settings.app_version,
    }


@app.get("/health/db")
def health_check_db() -> dict:
    """Health check de conectividade com PostgreSQL."""
    try:
        # Tenta fetch rápido para validar conexão
        db_client.fetch_vendas()
        return {
            "status": "healthy",
            "service": "database",
            "type": "postgresql",
        }
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return {
            "status": "unhealthy",
            "service": "database",
            "error": str(e),
        }
