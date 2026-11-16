"""Módulo de integração e validação de tokens do Google OAuth2."""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token


def verificar_token_google(
    credential: str,
    client_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Verifica e decodifica o ID Token emitido pelo Google Identity Services.

    Args:
        credential: JWT emitido pelo Google.
        client_id: O ID do Cliente OAuth configurado no Google Cloud Console.
                   Se omitido ou vazio, valida a assinatura e emissor sem checar audience.

    Returns:
        Dicionário com os dados verificados do usuário (email, name, sub, picture).

    Raises:
        HTTPException(401): Se o token for inválido, corrompido ou expirado.
        HTTPException(400): Se o e-mail não estiver verificado ou não existir no token.
    """
    try:
        request_transport = requests.Request()
        audience = client_id if client_id else None

        payload = id_token.verify_oauth2_token(
            id_token=credential,
            request=request_transport,
            audience=audience,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token do Google inválido ou expirado: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not payload.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail da conta Google não verificado.",
        )

    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token do Google não contém endereço de e-mail.",
        )

    return {
        "sub": payload.get("sub"),
        "email": email,
        "name": payload.get("name") or email.split("@")[0],
        "picture": payload.get("picture"),
    }
