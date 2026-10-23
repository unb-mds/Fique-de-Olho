from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.usuarios.schemas import (
    UsuarioCadastro,
    UsuarioLogin,
    UsuarioResposta,
)
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

    return criar_usuario(
        db=db,
        nome=dados.nome,
        email=dados.email,
        senha=dados.senha,
    )


@router.post("/login", response_model=UsuarioResposta)
def fazer_login(
    dados: UsuarioLogin,
    db: Session = Depends(get_db),
) -> UsuarioResposta:
    usuario = autenticar_usuario(
        db=db,
        email=dados.email,
        senha=dados.senha,
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )

    return usuario
