"""Testes do endpoint de feedback de usuários (RF07)."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, Feedback, get_db
from app.main import app


def _make_feedback_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestingSessionLocal


def test_post_feedback_persiste_e_envia_email_para_equipe(monkeypatch):
    TestingSessionLocal = _make_feedback_client()
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "fake-sg-key")
    monkeypatch.setattr(settings, "SENDGRID_FROM_EMAIL", "no-reply@fiquedeolho.unb.br")
    monkeypatch.setattr(settings, "FEEDBACK_TO_EMAIL", "fiquedeolho1011@gmail.com")

    try:
        with patch("app.modules.feedback.router.enviar_email", return_value=True) as mock_email:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/feedback",
                    json={
                        "tipo": "sugestao",
                        "mensagem": "Seria ótimo ter filtro de campus direto na página inicial.",
                        "email": "estudante@aluno.unb.br",
                        "pagina": "/",
                    },
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["tipo"] == "sugestao"
        assert body["email"] == "estudante@aluno.unb.br"
        assert body["id"] >= 1

        mock_email.assert_called_once()
        kwargs = mock_email.call_args.kwargs
        assert kwargs["destinatario"] == "fiquedeolho1011@gmail.com"
        assert "Sugestão" in kwargs["assunto"]
        assert "estudante@aluno.unb.br" in kwargs["html"]

        db = TestingSessionLocal()
        try:
            saved = db.query(Feedback).all()
            assert len(saved) == 1
            assert saved[0].tipo == "sugestao"
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_post_feedback_rejeita_mensagem_muito_curta():
    _make_feedback_client()
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/feedback",
                json={"tipo": "problema", "mensagem": "oi"},
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
