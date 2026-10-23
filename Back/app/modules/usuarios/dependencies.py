"""Dependências injetáveis do FastAPI para autenticação e autorização de usuários."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from app.core.database import Usuario, get_db
from app.modules.usuarios.security import decode_access_token
from app.modules.usuarios.service import buscar_usuario_por_id

# Esquema de autenticação HTTP Bearer para extração automática do header Authorization
http_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """Extrai e valida o token Bearer/JWT do header Authorization e retorna o usuário autenticado.

    Raises:
        HTTPException(401): Se as credenciais estiverem ausentes, o token for inválido/expirado
            ou o usuário não existir mais no banco.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de autenticação não fornecidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        usuario_id_str = payload.get("sub")
        if not usuario_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: identificador de usuário ausente.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        usuario_id = int(usuario_id_str)
    except (jwt.PyJWTError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    usuario = buscar_usuario_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário associado ao token não encontrado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return usuario

