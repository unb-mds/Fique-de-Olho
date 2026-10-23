from sqlalchemy.orm import Session

from app.core.database import Usuario
from app.modules.usuarios.security import get_password_hash, verify_password


def buscar_usuario_por_email(db: Session, email: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.email == email).first()


def criar_usuario(
    db: Session,
    nome: str,
    email: str,
    senha: str,
) -> Usuario:
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
) -> Usuario | None:
    usuario = buscar_usuario_por_email(db, email)
    if usuario is None or not verify_password(senha, usuario.senha_hash):
        return None
    return usuario