"""Testes automatizados para a gestão de favoritos integrados com autenticação JWT.

Atende a todos os critérios de aceite da Issue #65:
- Usuário autenticado consegue favoritar e desfavoritar editais.
- O ID do usuário na operação de favoritos vem obrigatoriamente do token Bearer.
- Usuários não autenticados recebem HTTP 401 Unauthorized.
- O mesmo usuário não duplica favoritos (idempotência).
- O usuário padrão fake não é criado para operações de favoritos.
- Listagem de favoritos retorna apenas os editais do usuário logado.
"""

from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, Favorito, StatusEdital, Usuario, get_db
from app.main import app
from app.modules.usuarios.security import create_access_token, get_password_hash


@pytest.fixture(autouse=True)
def db_session():
    """Cria banco SQLite em memória thread-safe para o TestClient."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
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

    # Cria segundo edital para testar listagem
    edital2 = Edital(
        id=2,
        titulo="Edital Estágio DEG 02/2026",
        url_pagina="https://deg.unb.br/editais/estagio-2026",
        campus="FGA",
        tipo="estagio",
        data_publicacao=datetime(2026, 9, 28),
        status=StatusEdital.ABERTO,
    )

    # Cria dois usuários para testes de isolamento
    usuario1 = Usuario(
        id=1,
        nome="Estudante Um",
        email="estudante1@aluno.unb.br",
        senha_hash=get_password_hash("senha_segura_1"),
    )
    usuario2 = Usuario(
        id=2,
        nome="Estudante Dois",
        email="estudante2@aluno.unb.br",
        senha_hash=get_password_hash("senha_segura_2"),
    )

    session.add_all([edital, edital2, usuario1, usuario2])
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


@pytest.fixture
def auth_headers_user1():
    """Gera header de autorização Bearer para o usuário 1."""
    token = create_access_token(
        data={"sub": "1", "email": "estudante1@aluno.unb.br"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user2():
    """Gera header de autorização Bearer para o usuário 2."""
    token = create_access_token(
        data={"sub": "2", "email": "estudante2@aluno.unb.br"}
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Testes de Favoritar Edital (POST)
# ---------------------------------------------------------------------------


def test_favoritar_edital_authenticated_success(
    client, db_session, auth_headers_user1
):
    """Usuário autenticado favorita edital com sucesso utilizando ID do token."""
    response = client.post("/api/v1/editais/1/favoritar", headers=auth_headers_user1)
    assert response.status_code == 200
    data = response.json()
    assert data["favoritado"] is True
    assert data["edital_id"] == 1
    assert data["usuario_id"] == 1

    # Verifica persistência no banco associada ao usuário 1
    fav = (
        db_session.query(Favorito)
        .filter_by(edital_id=1, usuario_id=1)
        .first()
    )
    assert fav is not None


def test_favoritar_edital_unauthenticated_returns_401(client, db_session):
    """Tentativa de favoritar sem token Bearer deve retornar HTTP 401."""
    response = client.post("/api/v1/editais/1/favoritar")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers

    # Garante que nenhum usuário padrão foi criado
    usuarios = db_session.query(Usuario).all()
    assert len(usuarios) == 2  # Apenas os 2 da fixture inicial


def test_favoritar_edital_invalid_token_returns_401(client):
    """Tentativa de favoritar com token corrompido deve retornar HTTP 401."""
    headers = {"Authorization": "Bearer token_falso_invalido"}
    response = client.post("/api/v1/editais/1/favoritar", headers=headers)
    assert response.status_code == 401


def test_favoritar_edital_not_found(client, auth_headers_user1):
    """Tentar favoritar edital inexistente retorna 404 mesmo autenticado."""
    response = client.post("/api/v1/editais/999/favoritar", headers=auth_headers_user1)
    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"].lower()


def test_favoritar_edital_idempotent(client, db_session, auth_headers_user1):
    """Favoritar o mesmo edital duas vezes não duplica registros no banco."""
    resp1 = client.post("/api/v1/editais/1/favoritar", headers=auth_headers_user1)
    assert resp1.status_code == 200

    resp2 = client.post("/api/v1/editais/1/favoritar", headers=auth_headers_user1)
    assert resp2.status_code == 200
    assert resp2.json()["favoritado"] is True

    contagem = (
        db_session.query(Favorito)
        .filter_by(edital_id=1, usuario_id=1)
        .count()
    )
    assert contagem == 1


# ---------------------------------------------------------------------------
# Testes de Desfavoritar Edital (DELETE)
# ---------------------------------------------------------------------------


def test_desfavoritar_edital_authenticated_success(
    client, db_session, auth_headers_user1
):
    """Usuário autenticado desfavorita edital com sucesso."""
    # Primeiro favorita
    client.post("/api/v1/editais/1/favoritar", headers=auth_headers_user1)

    # Depois desfavorita
    response = client.delete("/api/v1/editais/1/favoritar", headers=auth_headers_user1)
    assert response.status_code == 200
    data = response.json()
    assert data["favoritado"] is False
    assert data["edital_id"] == 1
    assert data["usuario_id"] == 1

    db_session.expire_all()
    fav = (
        db_session.query(Favorito)
        .filter_by(edital_id=1, usuario_id=1)
        .first()
    )
    assert fav is None


def test_desfavoritar_edital_unauthenticated_returns_401(client):
    """Tentativa de desfavoritar sem autenticação retorna 401."""
    response = client.delete("/api/v1/editais/1/favoritar")
    assert response.status_code == 401


def test_desfavoritar_edital_not_found(client, auth_headers_user1):
    """Desfavoritar edital inexistente retorna 404."""
    response = client.delete("/api/v1/editais/999/favoritar", headers=auth_headers_user1)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Testes de Listagem e Isolamento de Favoritos (GET)
# ---------------------------------------------------------------------------


def test_list_favoritos_authenticated_only_returns_own_editais(
    client, auth_headers_user1, auth_headers_user2
):
    """Listar favoritos deve retornar apenas os editais favoritados pelo usuário logado."""
    # Usuário 1 favorita edital 1
    client.post("/api/v1/editais/1/favoritar", headers=auth_headers_user1)

    # Usuário 2 favorita edital 2
    client.post("/api/v1/editais/2/favoritar", headers=auth_headers_user2)

    # Consulta do Usuário 1: deve conter apenas edital 1
    resp1 = client.get("/api/v1/editais/favoritos", headers=auth_headers_user1)
    assert resp1.status_code == 200
    favs_user1 = resp1.json()
    ids_user1 = [e["id"] for e in favs_user1]
    assert 1 in ids_user1
    assert 2 not in ids_user1

    # Consulta do Usuário 2: deve conter apenas edital 2
    resp2 = client.get("/api/v1/editais/favoritos", headers=auth_headers_user2)
    assert resp2.status_code == 200
    favs_user2 = resp2.json()
    ids_user2 = [e["id"] for e in favs_user2]
    assert 2 in ids_user2
    assert 1 not in ids_user2


def test_list_favoritos_unauthenticated_returns_401(client):
    """Consultar favoritos sem token deve retornar 401."""
    response = client.get("/api/v1/editais/favoritos")
    assert response.status_code == 401
