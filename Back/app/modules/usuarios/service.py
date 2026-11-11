"""Camada de serviço para regras de negócio do módulo de usuários."""

from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import Notificacao, Usuario, StatusNotificacao
from app.modules.usuarios.security import get_password_hash, verify_password


def buscar_usuario_por_email(db: Session, email: str) -> Optional[Usuario]:
    """Recupera um usuário a partir do e-mail cadastrado."""
    return db.query(Usuario).filter(Usuario.email == email).first()


def buscar_usuario_por_id(db: Session, usuario_id: int) -> Optional[Usuario]:
    """Recupera um usuário a partir da chave primária ID."""
    return db.query(Usuario).filter(Usuario.id == usuario_id).first()


def criar_usuario(
    db: Session,
    nome: str,
    email: str,
    senha: str,
) -> Usuario:
    """Cria e persiste um novo usuário no banco com senha hasheada com Argon2."""
    usuario = Usuario(
        nome=nome,
        email=email,
        senha_hash=get_password_hash(senha),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def autenticar_usuario(
    db: Session,
    email: str,
    senha: str,
) -> Optional[Usuario]:
    """Verifica e-mail e senha. Retorna a entidade Usuario se válido ou None se inválido."""
    usuario = buscar_usuario_por_email(db, email)
    if usuario is None or not verify_password(senha, usuario.senha_hash):
        return None
    return usuario


def atualizar_preferencia_email(
    db: Session,
    usuario_id: int,
    receber_emails: bool,
) -> Usuario:
    """Atualiza a preferência de recebimento de emails do usuário."""
    usuario = buscar_usuario_por_id(db, usuario_id)
    if usuario is None:
        raise ValueError("Usuário não encontrado.")

    usuario.receber_emails = receber_emails
    if not receber_emails:
        db.query(Notificacao).filter(
            Notificacao.usuario_id == usuario_id,
            Notificacao.status == StatusNotificacao.PENDENTE,
        ).delete(synchronize_session=False)
    db.commit()
    db.refresh(usuario)
    return usuario
