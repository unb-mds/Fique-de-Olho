"""Testes automatizados para login com o Google (OAuth2 / ID Token) - TDD.

Cobre:
- Validação e decodificação do ID Token do Google
- Tratamento de tokens inválidos, expirados ou com e-mail não verificado
- Cadastro automático de novo usuário no primeiro login com Google
- Autenticação de usuário já existente sem duplicidade no banco
- Emissão de Bearer/JWT compatível com a sessão do Fique de Olho
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Usuario, get_db
from app.main import app
from app.modules.usuarios.google_auth import verificar_token_google
from app.modules.usuarios.schemas import GoogleLoginRequest
from app.modules.usuarios.security import get_password_hash
from app.modules.usuarios.service import autenticar_ou_cadastrar_usuario_google


@pytest.fixture
def db_session():
    """Cria banco SQLite em memória isolado para os testes."""
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


# ---------------------------------------------------------------------------
# Testes Unitários da Camada de Verificação do Token do Google
# ---------------------------------------------------------------------------


def test_verificar_token_google_valido():
    """Valida que um token válido do Google retorna as informações do usuário."""
    mock_payload = {
        "sub": "google-user-12345",
        "email": "arthur@unb.br",
        "name": "Arthur Amaral",
        "email_verified": True,
        "picture": "https://example.com/avatar.jpg",
    }
    with patch(
        "app.modules.usuarios.google_auth.id_token.verify_oauth2_token",
        return_value=mock_payload,
    ):
        resultado = verificar_token_google("fake-valid-google-token", client_id="test-client-id")
        assert resultado["email"] == "arthur@unb.br"
        assert resultado["name"] == "Arthur Amaral"
        assert resultado["sub"] == "google-user-12345"


def test_verificar_token_google_invalido():
    """Garante que exceções da lib do Google gerem HTTPException 401."""
    with patch(
        "app.modules.usuarios.google_auth.id_token.verify_oauth2_token",
        side_effect=ValueError("Token expired or invalid signature"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            verificar_token_google("token-invalido", client_id="test-client-id")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Token do Google inválido" in exc_info.value.detail


def test_verificar_token_google_email_nao_verificado():
    """Rejeita contas Google cujo e-mail não foi verificado."""
    mock_payload = {
        "sub": "google-user-999",
        "email": "unverified@unb.br",
        "name": "Usuário Não Verificado",
        "email_verified": False,
    }
    with patch(
        "app.modules.usuarios.google_auth.id_token.verify_oauth2_token",
        return_value=mock_payload,
    ):
        with pytest.raises(HTTPException) as exc_info:
            verificar_token_google("token-email-nao-verificado", client_id="test-client-id")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "não verificado" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Testes Unitários de Regra de Negócio (Service)
# ---------------------------------------------------------------------------


def test_autenticar_ou_cadastrar_usuario_google_novo(db_session):
    """Cria um novo usuário caso o e-mail do Google ainda não exista no banco."""
    google_data = {
        "sub": "google-user-123",
        "email": "novo_google@unb.br",
        "name": "Novo Usuário Google",
    }

    usuario = autenticar_ou_cadastrar_usuario_google(db_session, google_data)

    assert usuario.id is not None
    assert usuario.email == "novo_google@unb.br"
    assert usuario.nome == "Novo Usuário Google"
    assert usuario.senha_hash is not None  # Senha aleatória e segura gerada automaticamente

    # Verifica se persistiu no banco
    salvo = db_session.query(Usuario).filter(Usuario.email == "novo_google@unb.br").first()
    assert salvo is not None
    assert salvo.id == usuario.id


def test_autenticar_ou_cadastrar_usuario_google_existente(db_session):
    """Retorna o usuário existente sem recriar ou duplicar registros."""
    # Cria usuário previamente com senha normal
    usuario_existente = Usuario(
        nome="Arthur Antigo",
        email="arthur_existente@unb.br",
        senha_hash=get_password_hash("minha_senha_123"),
    )
    db_session.add(usuario_existente)
    db_session.commit()
    db_session.refresh(usuario_existente)

    google_data = {
        "sub": "google-user-456",
        "email": "arthur_existente@unb.br",
        "name": "Arthur Antigo Atualizado",
    }

    usuario = autenticar_ou_cadastrar_usuario_google(db_session, google_data)

    assert usuario.id == usuario_existente.id
    assert usuario.email == "arthur_existente@unb.br"

    # Confirma que só existe 1 usuário com esse e-mail
    total = db_session.query(Usuario).filter(Usuario.email == "arthur_existente@unb.br").count()
    assert total == 1


# ---------------------------------------------------------------------------
# Testes de Integração da Rota /api/v1/auth/google
# ---------------------------------------------------------------------------


def test_endpoint_login_google_sucesso_novo_usuario(auth_client, db_session):
    """Testa o fluxo completo do endpoint com novo usuário via Google."""
    mock_payload = {
        "sub": "google-user-novo",
        "email": "arthuramaral2606@gmail.com",
        "name": "Arthur Amaral",
        "email_verified": True,
    }

    with patch(
        "app.modules.usuarios.google_auth.id_token.verify_oauth2_token",
        return_value=mock_payload,
    ):
        resposta = auth_client.post(
            "/api/v1/auth/google",
            json={"credential": "mock-valid-google-id-token"},
        )

    assert resposta.status_code == status.HTTP_200_OK
    dados = resposta.json()
    assert "access_token" in dados
    assert dados["token_type"].lower() == "bearer"
    assert dados["usuario"]["email"] == "arthuramaral2606@gmail.com"
    assert dados["usuario"]["nome"] == "Arthur Amaral"


def test_endpoint_login_google_sucesso_usuario_existente(auth_client, db_session):
    """Testa o fluxo do endpoint com usuário já existente."""
    usuario_existente = Usuario(
        nome="Arthur Existente",
        email="arthuramaral2606@gmail.com",
        senha_hash=get_password_hash("senha_existente"),
    )
    db_session.add(usuario_existente)
    db_session.commit()

    mock_payload = {
        "sub": "google-user-existente",
        "email": "arthuramaral2606@gmail.com",
        "name": "Arthur Existente",
        "email_verified": True,
    }

    with patch(
        "app.modules.usuarios.google_auth.id_token.verify_oauth2_token",
        return_value=mock_payload,
    ):
        resposta = auth_client.post(
            "/api/v1/auth/google",
            json={"credential": "mock-valid-google-id-token"},
        )

    assert resposta.status_code == status.HTTP_200_OK
    dados = resposta.json()
    assert dados["usuario"]["id"] == usuario_existente.id
    assert dados["usuario"]["email"] == "arthuramaral2606@gmail.com"


def test_endpoint_login_google_token_invalido(auth_client):
    """Testa resposta 401 caso o token do Google seja recusado."""
    with patch(
        "app.modules.usuarios.google_auth.id_token.verify_oauth2_token",
        side_effect=ValueError("Token signature is invalid"),
    ):
        resposta = auth_client.post(
            "/api/v1/auth/google",
            json={"credential": "mock-invalid-google-token"},
        )

    assert resposta.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Token do Google inválido" in resposta.json()["detail"]
