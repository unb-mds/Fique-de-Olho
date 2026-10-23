"""Módulo de segurança e criptografia para o módulo de usuários.

Implementa hashing seguro de senhas com Argon2 (via pwdlib) e emissão /
validação de tokens de autenticação Bearer/JWT (Issue #63).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

# Contexto de hashing de senhas (Argon2 recomendado)
pwd_context = PasswordHash.recommended()

# Campos sensíveis que jamais devem ser serializados no payload do token
SENSITIVE_FIELDS = {"senha", "senha_hash", "password"}


def get_password_hash(password: str) -> str:
    """Gera o hash seguro da senha em texto puro."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto puro corresponde ao hash armazenado."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Gera um token JWT com expiração e payload limpo de dados sensíveis.

    Args:
        data: Dicionário contendo as claims do token (ex: sub, email).
        expires_delta: Tempo opcional até a expiração. Se não fornecido,
            utiliza o padrão configurado em `settings.ACCESS_TOKEN_EXPIRE_MINUTES`.

    Returns:
        Token JWT codificado como string.
    """
    to_encode = {k: v for k, v in data.items() if k not in SENSITIVE_FIELDS}

    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode["exp"] = expire
    to_encode["iat"] = now

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodifica e valida a assinatura e expiração de um token JWT.

    Args:
        token: Token JWT serializado.

    Returns:
        Dicionário com o payload decodificado.

    Raises:
        jwt.PyJWTError: Se o token for inválido, malformado ou expirado.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
