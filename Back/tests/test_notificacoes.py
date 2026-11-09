from datetime import date

import pytest
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
from app.modules.scraper.pipeline import gerar_notificacoes_prazo, upsert_edital


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


def _criar_favorito(db_session, fim_inscricao=date(2026, 11, 6)):
    usuario = Usuario(nome="Ana", email="ana@example.com", senha_hash="hash")
    edital = Edital(
        titulo="Edital de monitoria",
        url_pagina="https://example.com/monitoria",
        fim_inscricao=fim_inscricao,
        hash_conteudo="hash-inicial",
    )
    db_session.add_all([usuario, edital])
    db_session.flush()
    db_session.add(Favorito(usuario_id=usuario.id, edital_id=edital.id))
    db_session.commit()
    return usuario, edital


def test_edital_alterado_notifica_favoritos_sem_duplicar(db_session):
    usuario, edital = _criar_favorito(db_session)

    upsert_edital(
        db_session,
        {
            "titulo": edital.titulo,
            "link": edital.url_pagina,
            "hash_conteudo": "hash-alterado",
            "fim_inscricao": "06/11/2026",
        },
    )
    upsert_edital(
        db_session,
        {
            "titulo": edital.titulo,
            "link": edital.url_pagina,
            "hash_conteudo": "hash-alterado",
            "fim_inscricao": "06/11/2026",
        },
    )

    notificacoes = db_session.query(Notificacao).all()
    assert len(notificacoes) == 1
    assert notificacoes[0].usuario_id == usuario.id
    assert notificacoes[0].edital_id == edital.id
    assert notificacoes[0].tipo == TipoNotificacao.EDITAL_ATUALIZADO
    assert notificacoes[0].status == StatusNotificacao.PENDENTE


def test_edital_inalterado_nao_notifica(db_session):
    _criar_favorito(db_session)

    upsert_edital(
        db_session,
        {
            "titulo": "Edital de monitoria",
            "link": "https://example.com/monitoria",
            "hash_conteudo": "hash-inicial",
        },
    )

    assert db_session.query(Notificacao).count() == 0


def test_gera_alertas_de_tres_dias_um_dia_e_no_dia(db_session):
    _, edital = _criar_favorito(db_session, fim_inscricao=date(2026, 11, 6))

    assert gerar_notificacoes_prazo(db_session, date(2026, 11, 3)) == 1
    assert gerar_notificacoes_prazo(db_session, date(2026, 11, 5)) == 1
    assert gerar_notificacoes_prazo(db_session, date(2026, 11, 6)) == 1
    assert gerar_notificacoes_prazo(db_session, date(2026, 11, 6)) == 0

    notificacoes = (
        db_session.query(Notificacao)
        .filter(Notificacao.edital_id == edital.id)
        .order_by(Notificacao.id)
        .all()
    )
    assert [n.tipo for n in notificacoes] == [
        TipoNotificacao.PRAZO_ENCERRANDO,
        TipoNotificacao.PRAZO_ENCERRANDO,
        TipoNotificacao.PRAZO_ENCERRANDO,
    ]
    assert [n.chave_evento for n in notificacoes] == [
        "prazo:2026-11-03",
        "prazo:2026-11-05",
        "prazo:2026-11-06",
    ]
