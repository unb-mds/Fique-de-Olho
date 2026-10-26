"""Rotas da API para registro, login e identificação de usuários (Issue #63)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import Usuario, get_db
from app.modules.usuarios.dependencies import get_current_user
from app.modules.usuarios.schemas import (
    TokenResposta,
    UsuarioCadastro,
    UsuarioLogin,
    UsuarioResposta,
)
from app.modules.usuarios.security import create_access_token
from app.modules.usuarios.service import (
    autenticar_usuario,
    buscar_usuario_por_email,
    criar_usuario,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/register",
    response_model=UsuarioResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar novo usuário",
    description="Cria uma nova conta de usuário com senha criptografada via Argon2.",
)
def registrar_usuario(
    dados: UsuarioCadastro,
    db: Session = Depends(get_db),
) -> UsuarioResposta:
    if buscar_usuario_por_email(db, dados.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado.",
        )

    usuario = criar_usuario(
        db=db,
        nome=dados.nome,
        email=dados.email,
        senha=dados.senha,
    )
    return usuario


@router.post(
    "/login",
    response_model=TokenResposta,
    summary="Autenticar usuário e obter Bearer/JWT",
    description="Autentica com e-mail e senha, retornando o token Bearer/JWT para requisições autenticadas.",
)
def fazer_login(
    dados: UsuarioLogin,
    db: Session = Depends(get_db),
) -> TokenResposta:
    usuario = autenticar_usuario(
        db=db,
        email=dados.email,
        senha=dados.senha,
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Gera token JWT contendo apenas informações públicas (sem senha ou hash)
    access_token = create_access_token(
        data={"sub": str(usuario.id), "email": usuario.email}
    )

    return TokenResposta(
        access_token=access_token,
        token_type="bearer",
        usuario=usuario,
    )


@router.get(
    "/me",
    response_model=UsuarioResposta,
    summary="Obter usuário atualmente autenticado",
    description="Recupera o perfil do usuário autenticado a partir do cabeçalho `Authorization: Bearer <token>`.",
)
def obter_usuario_logado(
    usuario_atual: Usuario = Depends(get_current_user),
) -> UsuarioResposta:
    return usuario_atual
