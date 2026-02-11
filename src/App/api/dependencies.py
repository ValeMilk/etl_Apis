"""Dependency injection para FastAPI com autenticação Bearer."""
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from App.core.config import settings


logger = logging.getLogger(__name__)
security = HTTPBearer(
    scheme_name="Bearer Token",
    description="Token de autenticação para acesso às rotas protegidas",
    auto_error=True,
)


async def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> str:
    """
    Valida o Bearer token contra o token configurado.
    
    Args:
        credentials: Credenciais HTTP Bearer extraídas do header
        
    Returns:
        Token validado (string)
        
    Raises:
        HTTPException: 401 se token inválido ou ausente
    """
    token = credentials.credentials
    expected_token = settings.api_auth_token.get_secret_value()
    
    if token != expected_token:
        logger.warning("Invalid authentication token attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token


# Dependency para rotas protegidas
TokenDep = Annotated[str, Depends(verify_token)]
