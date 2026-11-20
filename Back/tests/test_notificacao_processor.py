from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import (
    AlertaEdital,
    Base,
    Edital,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
    Usuario,
    get_db,
)
from app.main import app
from app.modules.notificacoes.processor import processar_notificacoes_pendentes
from app.modules.notificacoes.service import data_hoje_brasilia, gerar_notificacoes_prazo
from app.modules.usuarios.security import create_access_token


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_processa_notificacao_pendente_e_marca_como_enviada(monkeypatch):
    db = _session()
    usuario = Usuario(
        nome="Arthur",
        email="arthuramaral2606@gmail.com",
        senha_hash="hash",
    )
    edital = Edital(
        titulo="Edital de monitoria",
        url_pagina="https://example.com/monitoria",
        fim_inscricao=date(2026, 11, 30),
    )
    db.add_all([usuario, edital])
    db.flush()
    db.add(AlertaEdital(usuario_id=usuario.id, edital_id=edital.id))
    notificacao = Notificacao(
        usuario_id=usuario.id,
        edital_id=edital.id,
        tipo=TipoNotificacao.EDITAL_ATUALIZADO,
        chave_evento="alteracao:abc",
    )
    db.add(notificacao)
    db.commit()

    enviados = []

    def enviar_email(**kwargs):
        enviados.append(kwargs)
        return True

    monkeypatch.setattr(
        "app.modules.notificacoes.processor.enviar_email",
        enviar_email,
    )

    resultado = processar_notificacoes_pendentes(
        db,
        api_key="SG.test-key",
        remetente="fiquedeolho1011@gmail.com",
        backoff_seconds=0,
    )

    assert resultado == {"enviadas": 1, "falhas": 0}
    assert enviados[0]["destinatario"] == "arthuramaral2606@gmail.com"
    assert db.get(Notificacao, notificacao.id).status == StatusNotificacao.ENVIADA


def test_processa_notificacao_quando_edital_nao_tem_url_pagina(monkeypatch):
    db = _session()
    usuario = Usuario(nome="Arthur", email="arthur@example.com", senha_hash="hash")
    edital = Edital(
        titulo="Edital sem URL pagina",
        url_pagina=None,
        url_pdf="https://example.com/edital.pdf",
    )
    db.add_all([usuario, edital])
    db.flush()
    notificacao = Notificacao(
        usuario_id=usuario.id,
        edital_id=edital.id,
        tipo=TipoNotificacao.PRAZO_ENCERRANDO,
        chave_evento="prazo:2026-11-19",
    )
    db.add(notificacao)
    db.commit()

    enviados = []
    monkeypatch.setattr(
        "app.modules.notificacoes.processor.enviar_email",
        lambda **kwargs: enviados.append(kwargs) or True,
    )

    resultado = processar_notificacoes_pendentes(
        db,
        api_key="SG.test-key",
        remetente="fiquedeolho1011@gmail.com",
        backoff_seconds=0,
    )

    assert resultado == {"enviadas": 1, "falhas": 0}
    assert "https://example.com/edital.pdf" in enviados[0]["html"]


def test_reenvia_falha_transitoria_ate_tres_tentativas(monkeypatch):
    db = _session()
    usuario = Usuario(nome="Arthur", email="arthur@example.com", senha_hash="hash")
    edital = Edital(
        titulo="Edital de monitoria",
        url_pagina="https://example.com/monitoria",
    )
    db.add_all([usuario, edital])
    db.flush()
    db.add(
        Notificacao(
            usuario_id=usuario.id,
            edital_id=edital.id,
            tipo=TipoNotificacao.EDITAL_ATUALIZADO,
            chave_evento="alteracao:abc",
        )
    )
    db.commit()

    tentativas = []

    def enviar_email(**kwargs):
        tentativas.append(kwargs)
        if len(tentativas) < 3:
            raise RuntimeError("SendGrid indisponivel")
        return True

    monkeypatch.setattr(
        "app.modules.notificacoes.processor.enviar_email",
        enviar_email,
    )

    resultado = processar_notificacoes_pendentes(
        db,
        api_key="SG.test-key",
        remetente="fiquedeolho1011@gmail.com",
        backoff_seconds=0,
    )

    assert resultado == {"enviadas": 1, "falhas": 0}
    assert len(tentativas) == 3


def test_nao_envia_notificacao_para_usuario_com_emails_desativados(monkeypatch):
    db = _session()
    usuario = Usuario(
        nome="Arthur",
        email="arthur@example.com",
        senha_hash="hash",
        receber_emails=False,
    )
    edital = Edital(
        titulo="Edital de monitoria",
        url_pagina="https://example.com/monitoria",
    )
    db.add_all([usuario, edital])
    db.flush()
    notificacao = Notificacao(
        usuario_id=usuario.id,
        edital_id=edital.id,
        tipo=TipoNotificacao.EDITAL_ATUALIZADO,
        chave_evento="alteracao:abc",
    )
    db.add(notificacao)
    db.commit()

    monkeypatch.setattr(
        "app.modules.notificacoes.processor.enviar_email",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("email nao deveria ser enviado")
        ),
    )

    resultado = processar_notificacoes_pendentes(
        db,
        api_key="SG.test-key",
        remetente="fiquedeolho1011@gmail.com",
        backoff_seconds=0,
    )

    assert resultado == {"enviadas": 0, "falhas": 0}
    assert db.get(Notificacao, notificacao.id).status == StatusNotificacao.PENDENTE


def test_fluxo_alerta_prazo_gera_e_envia_notificacao(monkeypatch):
    db = _session()
    usuario = Usuario(
        nome="Arthur",
        email="arthur@example.com",
        senha_hash="hash",
    )
    edital = Edital(
        titulo="Edital com prazo",
        url_pagina="https://example.com/prazo",
        fim_inscricao=date(2026, 11, 13),
    )
    db.add_all([usuario, edital])
    db.flush()
    db.add(AlertaEdital(usuario_id=usuario.id, edital_id=edital.id))
    db.commit()

    assert gerar_notificacoes_prazo(db, date(2026, 11, 10)) == 1

    enviados = []
    monkeypatch.setattr(
        "app.modules.notificacoes.processor.enviar_email",
        lambda **kwargs: enviados.append(kwargs) or True,
    )

    resultado = processar_notificacoes_pendentes(
        db,
        api_key="SG.test-key",
        remetente="fiquedeolho@example.com",
        backoff_seconds=0,
    )

    assert resultado == {"enviadas": 1, "falhas": 0}
    assert enviados[0]["destinatario"] == "arthur@example.com"
    assert db.query(Notificacao).one().status == StatusNotificacao.ENVIADA


def test_endpoint_alertas_ativa_envia_prazo_imediato_e_confirmacao(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    hoje = data_hoje_brasilia()
    usuario = Usuario(
        id=1,
        nome="Arthur",
        email="arthur@example.com",
        senha_hash="hash",
        receber_emails=False,
    )
    edital_urgente = Edital(
        id=10,
        titulo="Seleção Doutorado Zoologia",
        url_pagina="https://example.com/zoologia",
        fim_inscricao=hoje + timedelta(days=1),
    )
    edital_futuro = Edital(
        id=20,
        titulo="Edital futuro",
        url_pagina="https://example.com/futuro",
        fim_inscricao=hoje + timedelta(days=15),
    )
    db.add_all([usuario, edital_urgente, edital_futuro])
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "SG.test-key")
    monkeypatch.setattr(settings, "SENDGRID_FROM_EMAIL", "fiquedeolho@example.com")
    monkeypatch.setattr(settings, "NOTIFICATION_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "SCRAPER_SCHEDULER_ENABLED", False)

    enviados = []
    monkeypatch.setattr(
        "app.modules.notificacoes.processor.enviar_email",
        lambda **kwargs: enviados.append(kwargs) or True,
    )

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(data={"sub": "1", "email": "arthur@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with TestClient(app) as client:
            # Sem token retorna 401
            assert client.post("/api/v1/editais/10/alertas").status_code == 401

            # Ativa sino em edital com 1 dia restante -> gera PRAZO_ENCERRANDO e envia imediatamente
            resp_urgente = client.post("/api/v1/editais/10/alertas", headers=headers)
            assert resp_urgente.status_code == 200
            assert resp_urgente.json()["notificar_email"] is True

            # Ativa sino em edital futuro -> envia confirmação imediata
            resp_futuro = client.post("/api/v1/editais/20/alertas", headers=headers)
            assert resp_futuro.status_code == 200
            assert resp_futuro.json()["notificar_email"] is True

            # Lista alertas ativos
            resp_lista = client.get("/api/v1/editais/alertas", headers=headers)
            assert resp_lista.status_code == 200
            assert resp_lista.json()["edital_ids"] == [10, 20]

            # Desativa alerta do edital 10
            resp_del = client.delete("/api/v1/editais/10/alertas", headers=headers)
            assert resp_del.status_code == 200
            assert resp_del.json()["notificar_email"] is False

            resp_lista_depois = client.get("/api/v1/editais/alertas", headers=headers)
            assert resp_lista_depois.json()["edital_ids"] == [20]
    finally:
        app.dependency_overrides.clear()

    assert len(enviados) == 2
    assert "Prazo de inscrição se aproximando" in enviados[0]["assunto"]
    assert "Alertas ativados" in enviados[1]["assunto"]
