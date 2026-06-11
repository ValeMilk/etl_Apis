"""Configurações da aplicação usando Pydantic Settings."""
from typing import List, Union

from pydantic import Field, field_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações da aplicação com validação automática via Pydantic.
    Variáveis carregadas do .env ou environment variables.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    db_url: str = Field(..., description="PostgreSQL connection string")
    database_echo: bool = Field(default=False, description="Echo SQL queries")

    # API Cometa (External)
    api_base_url: str = Field(..., description="Cometa API base URL")
    api_email: str = Field(..., description="Cometa API email")
    api_password: SecretStr = Field(..., description="Cometa API password")
    verify_ssl: bool = Field(default=False, description="Verify SSL certificates")
    request_timeout: int = Field(default=30, ge=5, le=300, description="Request timeout in seconds")
    token_refresh_hours: int = Field(default=12, ge=1, le=23, description="Hours before forcing token refresh (Cometa token expires daily)")

    # API Cometa - ValeFish
    valefish_api_email: str = Field(default="", description="ValeFish API email")
    valefish_api_password: SecretStr = Field(default="", description="ValeFish API password")

    # Security (FastAPI Auth)
    api_auth_token: SecretStr = Field(..., description="Bearer token for API authentication")
    cors_origins: Union[str, List[str]] = Field(
        default="*",
        description="CORS allowed origins (comma-separated string or list)"
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # ETL Schedule
    etl_interval_minutes: int = Field(default=480, ge=1, le=1440, description="ETL interval in minutes (480 = 3x/day)")

    # InfoMarket API
    infomarket_email: str = Field(default="", description="InfoMarket API email")
    infomarket_password: SecretStr = Field(default="", description="InfoMarket API password")
    infomarket_lookback_days: int = Field(default=90, ge=0, description="Dias para lookback InfoMarket")
    infomarket_lookahead_days: int = Field(default=60, ge=1, description="Dias para lookahead InfoMarket")

    # FastAPI
    app_title: str = Field(default="BI_COMETA", description="API title")
    app_version: str = Field(default="1.1.0", description="API version")
    app_host: str = Field(default="0.0.0.0", description="API host")
    app_port: int = Field(default=8000, ge=1024, le=65535, description="API port")
    app_environment: str = Field(default="production", description="Environment: development, staging, production")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Valida e normaliza log level."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins de string ou lista."""
        if isinstance(v, str):
            # Split por vírgula e remove whitespace
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]  # Fallback

    @property
    def is_production(self) -> bool:
        """Verifica se está em produção."""
        return self.app_environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Verifica se está em desenvolvimento."""
        return self.app_environment.lower() == "development"


# Singleton global
settings = Settings()
