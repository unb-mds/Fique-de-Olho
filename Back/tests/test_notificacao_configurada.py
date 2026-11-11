import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.modules.notificacoes.processor import (
    processar_notificacoes_configuradas,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_processador_configurado_exige_chave_e_remetente(monkeypatch, db_session):
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "")
    monkeypatch.setattr(settings, "SENDGRID_FROM_EMAIL", "")

    with pytest.raises(RuntimeError, match="SendGrid"):
        processar_notificacoes_configuradas(db_session)
