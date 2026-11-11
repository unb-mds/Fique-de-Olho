from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import (
    Base,
    Edital,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
    Usuario,
)
from app.modules.usuarios.service import atualizar_preferencia_email


def test_usuario_pode_desativar_emails_de_notificacao():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    usuario = Usuario(
        nome="Arthur",
        email="arthur@example.com",
        senha_hash="hash",
    )
    db.add(usuario)
    db.commit()

    atualizado = atualizar_preferencia_email(db, usuario.id, False)

    assert atualizado.receber_emails is False
    assert db.get(Usuario, usuario.id).receber_emails is False


def test_desativar_emails_descarta_notificacoes_pendentes():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    usuario = Usuario(nome="Arthur", email="arthur@example.com", senha_hash="hash")
    edital = Edital(titulo="Edital", url_pagina="https://example.com/edital")
    db.add_all([usuario, edital])
    db.commit()
    db.add(
        Notificacao(
            usuario_id=usuario.id,
            edital_id=edital.id,
            tipo=TipoNotificacao.EDITAL_ATUALIZADO,
            status=StatusNotificacao.PENDENTE,
            chave_evento="alteracao:1",
        )
    )
    db.commit()

    atualizar_preferencia_email(db, usuario.id, False)

    assert db.query(Notificacao).count() == 0
