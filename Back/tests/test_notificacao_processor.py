from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import (
    Base,
    Edital,
    Favorito,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
    Usuario,
)
from app.modules.notificacoes.processor import processar_notificacoes_pendentes
from app.modules.notificacoes.service import gerar_notificacoes_prazo


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
    db.add(
        Favorito(usuario_id=usuario.id, edital_id=edital.id)
    )
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


def test_fluxo_favorito_prazo_gera_e_envia_notificacao(monkeypatch):
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
    db.add(Favorito(usuario_id=usuario.id, edital_id=edital.id))
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
