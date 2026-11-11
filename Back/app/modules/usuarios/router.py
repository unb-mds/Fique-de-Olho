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
    PreferenciaEmailAtualizacao,
)
from app.modules.usuarios.security import create_access_token
from app.modules.notificacoes.schemas import NotificacaoResposta
from app.modules.notificacoes.service import listar_notificacoes_usuario
from app.modules.usuarios.service import (
    autenticar_usuario,
    buscar_usuario_por_email,
    criar_usuario,
    atualizar_preferencia_email,
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


@router.patch(
    "/me/email-preferences",
    response_model=UsuarioResposta,
    summary="Atualizar preferência de emails",
)
def atualizar_preferencia_email_usuario(
    dados: PreferenciaEmailAtualizacao,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
) -> UsuarioResposta:
    return atualizar_preferencia_email(
        db,
        usuario_atual.id,
        dados.receber_emails,
    )


@router.get(
    "/me/notifications",
    response_model=list[NotificacaoResposta],
    summary="Listar histórico de notificações",
)
def listar_notificacoes_usuario_atual(
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
) -> list[NotificacaoResposta]:
    notificacoes = listar_notificacoes_usuario(db, usuario_atual.id)
    return [
        NotificacaoResposta(
            id=notificacao.id,
            edital_id=notificacao.edital_id,
            edital_titulo=notificacao.edital.titulo,
            tipo=notificacao.tipo,
            status=notificacao.status,
            criada_em=notificacao.criada_em,
            enviada_em=notificacao.enviada_em,
        )
        for notificacao in notificacoes
    ]
