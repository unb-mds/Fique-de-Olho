"""Testes de autenticação persistente com Bearer/JWT (TDD).

Cobre os critérios de aceite da Issue #63:
- Login com credenciais válidas retorna token Bearer/JWT.
- Credenciais inválidas retornam HTTP 401.
- Backend obtém o usuário autenticado via cabeçalho Authorization: Bearer <token>.
- Token não contém senha nem hash de senha.
- Cadastro persiste o usuário no banco de dados.
- Validação de tokens expirados e inválidos.
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, Usuario, get_db
from app.main import app
from app.modules.usuarios.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
)


@pytest.fixture
def db_session():
    """Cria banco SQLite em memória isolado para os testes de autenticação."""
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
def auth_client(db_session):
    """TestClient configurado com o banco isolado."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def usuario_teste(db_session):
    """Cria um usuário padrão para testes."""
    usuario = Usuario(
        nome="Lucas Silva",
        email="lucas@unb.br",
        senha_hash=get_password_hash("senha_segura_123"),
    )
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


# ---------------------------------------------------------------------------
# Testes unitários de geração e validação de tokens JWT
# ---------------------------------------------------------------------------


def test_create_access_token_has_subject_and_expiration():
    """Gera um token e verifica campos essenciais no payload."""
    payload = {"sub": "1", "email": "teste@unb.br"}
    token = create_access_token(data=payload)

    decoded = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert decoded["sub"] == "1"
    assert decoded["email"] == "teste@unb.br"
    assert "exp" in decoded


def test_token_does_not_contain_password_or_hash():
    """Garante que dados sensíveis de credenciais nunca vazem no token."""
    payload = {
        "sub": "2",
        "email": "seguro@unb.br",
        "senha": "123",
        "senha_hash": "hash123",
    }
    token = create_access_token(data=payload)
    decoded = decode_access_token(token)

    assert "senha" not in decoded
    assert "senha_hash" not in decoded


def test_decode_expired_token_raises_or_returns_none():
    """Token expirado deve ser rejeitado."""
    expired_delta = timedelta(minutes=-10)
    token = create_access_token(
        data={"sub": "1"}, expires_delta=expired_delta
    )

    with pytest.raises(Exception):
        decode_access_token(token)


def test_decode_invalid_token_signature_raises_or_returns_none():
    """Token adulterado ou com assinatura incorreta deve falhar."""
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.invalidsignature"

    with pytest.raises(Exception):
        decode_access_token(fake_token)


# ---------------------------------------------------------------------------
# Testes de integração dos endpoints /auth/register, /auth/login e /auth/me
# ---------------------------------------------------------------------------


def test_register_persists_user_in_database(auth_client, db_session):
    """Cadastro deve persistir o usuário com hash seguro no banco."""
    dados_cadastro = {
        "nome": "Mariana Souza",
        "email": "mariana@unb.br",
        "senha": "senha_forte_2026",
    }
    response = auth_client.post("/api/v1/auth/register", json=dados_cadastro)

    assert response.status_code == 201
    corpo = response.json()
    assert corpo["nome"] == "Mariana Souza"
    assert corpo["email"] == "mariana@unb.br"
    assert "senha" not in corpo
    assert "senha_hash" not in corpo

    # Verifica persistência no banco
    usuario_db = db_session.query(Usuario).filter_by(email="mariana@unb.br").first()
    assert usuario_db is not None
    assert usuario_db.senha_hash != "senha_forte_2026"
    assert usuario_db.senha_hash.startswith("$")


def test_login_successful_returns_bearer_jwt_token(auth_client, usuario_teste):
    """Login com credenciais válidas deve retornar access_token e token_type bearer."""
    dados_login = {
        "email": "lucas@unb.br",
        "senha": "senha_segura_123",
    }
    response = auth_client.post("/api/v1/auth/login", json=dados_login)

    assert response.status_code == 200
    corpo = response.json()
    assert "access_token" in corpo
    assert corpo["token_type"].lower() == "bearer"
    assert "usuario" in corpo
    assert corpo["usuario"]["email"] == "lucas@unb.br"

    # Valida que o token retornado é decodificável
    decoded = decode_access_token(corpo["access_token"])
    assert decoded["sub"] == str(usuario_teste.id)
    assert decoded["email"] == usuario_teste.email
    assert "senha" not in decoded
    assert "senha_hash" not in decoded


def test_login_invalid_password_returns_401(auth_client, usuario_teste):
    """Tentativa de login com senha incorreta deve retornar HTTP 401."""
    dados_login = {
        "email": "lucas@unb.br",
        "senha": "senha_errada_xyz",
    }
    response = auth_client.post("/api/v1/auth/login", json=dados_login)

    assert response.status_code == 401
    assert "inválidos" in response.json()["detail"].lower()


def test_login_nonexistent_user_returns_401(auth_client):
    """Tentativa de login com e-mail inexistente deve retornar HTTP 401."""
    dados_login = {
        "email": "inexistente@unb.br",
        "senha": "senha_qualquer",
    }
    response = auth_client.post("/api/v1/auth/login", json=dados_login)

    assert response.status_code == 401


def test_get_current_user_with_valid_token(auth_client, usuario_teste):
    """Endpoint /auth/me protegido obtém o usuário autenticado pelo cabeçalho Authorization."""
    token = create_access_token(
        data={"sub": str(usuario_teste.id), "email": usuario_teste.email}
    )

    headers = {"Authorization": f"Bearer {token}"}
    response = auth_client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["id"] == usuario_teste.id
    assert corpo["email"] == usuario_teste.email
    assert corpo["nome"] == usuario_teste.nome


def test_get_current_user_with_invalid_token(auth_client):
    """Requisição com token inválido deve retornar HTTP 401."""
    headers = {"Authorization": "Bearer token_completamente_invalido"}
    response = auth_client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401


def test_get_current_user_without_token(auth_client):
    """Requisição a endpoint protegido sem token deve retornar HTTP 401."""
    response = auth_client.get("/api/v1/auth/me")

    assert response.status_code == 401

