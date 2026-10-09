from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, Favorito, StatusEdital, Usuario, get_db
from app.main import app


@pytest.fixture
def db_session():
    """Cria banco SQLite em memória thread-safe para o TestClient."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Cria edital de teste
    edital = Edital(
        id=1,
        titulo="Edital Monitoria DEG 01/2026",
        url_pagina="https://deg.unb.br/editais/monitoria-2026",
        campus="Darcy Ribeiro",
        tipo="monitoria",
        data_publicacao=datetime(2026, 9, 27),
        status=StatusEdital.ABERTO,
    )
    # Cria usuário de teste
    usuario = Usuario(
        id=1,
        nome="Estudante UnB",
        email="estudante@aluno.unb.br",
        senha_hash="hash_teste",
    )
    session.add_all([edital, usuario])
    session.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_favoritar_edital_success(client, db_session):
    response = client.post("/editais/1/favoritar")
    assert response.status_code == 200
    data = response.json()
    assert data["favoritado"] is True
    assert data["edital_id"] == 1

    # Verifica persistência no banco
    fav = db_session.query(Favorito).filter_by(edital_id=1, usuario_id=1).first()
    assert fav is not None


def test_favoritar_edital_prefix_api_v1(client, db_session):
    response = client.post("/api/v1/editais/1/favoritar")
    assert response.status_code == 200
    assert response.json()["favoritado"] is True


def test_favoritar_edital_not_found(client, db_session):
    response = client.post("/editais/999/favoritar")
    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"]


def test_desfavoritar_edital_success(client, db_session):
    # Primeiro favorita
    client.post("/editais/1/favoritar")

    # Depois desfavorita
    response = client.delete("/editais/1/favoritar")
    assert response.status_code == 200
    data = response.json()
    assert data["favoritado"] is False
    assert data["edital_id"] == 1

    # Atualiza a sessão para refletir mudanças do endpoint
    db_session.expire_all()
    fav = db_session.query(Favorito).filter_by(edital_id=1, usuario_id=1).first()
    assert fav is None


def test_desfavoritar_edital_not_found(client, db_session):
    response = client.delete("/editais/999/favoritar")
    assert response.status_code == 404
