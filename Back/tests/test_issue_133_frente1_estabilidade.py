"""Testes da Issue #133 (Frente 1) — Estabilidade Render/Neon, mitigação OOM e locks."""

import asyncio
from collections import OrderedDict
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import (
    Base,
    Edital,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
    Usuario,
    build_db_connect_args,
    get_db,
)
from app.main import app, ping, root
from app.modules.editais.service import _EDITAIS_CACHE, invalidar_cache_editais, listar_editais_com_cache
from app.modules.notificacoes.email_service import SENDGRID_TIMEOUT_SECONDS, enviar_email
from app.modules.notificacoes.processor import processar_notificacoes_pendentes
from app.modules.scraper import pdf as pdf_mod
from app.modules.scraper.scheduler import SCRAPER_SYNC_LOCK, executar_ciclo_scraping
from app.modules.usuarios.security import get_password_hash
from app.modules.usuarios.service import autenticar_usuario, criar_usuario


def _make_sqlite_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_ping_e_root_sao_assincronos(client):
    assert asyncio.iscoroutinefunction(ping)
    assert asyncio.iscoroutinefunction(root)

    resp_root = client.get("/", follow_redirects=False)
    assert resp_root.status_code in (302, 307)
    assert resp_root.headers.get("location") == "/docs"


def test_database_connect_timeout_condicionado_ao_postgresql():
    assert build_db_connect_args("postgresql+psycopg2://u:p@localhost:5432/db") == {"connect_timeout": 15}
    assert build_db_connect_args("postgresql://u:p@host/db") == {"connect_timeout": 15}
    assert build_db_connect_args("sqlite:///./test.db") == {}


def test_gemini_model_default_e_gemini_3_5_flash_lite(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    from app.core.config import Settings

    cfg = Settings(_env_file=None)
    assert cfg.GEMINI_MODEL == "gemini-3.5-flash-lite"

    render_yaml = Path(__file__).resolve().parents[2] / "render.yaml"
    assert "value: gemini-3.5-flash-lite" in render_yaml.read_text(encoding="utf-8")


def test_extract_pdf_chama_flush_cache_e_preserva_anexos_finais(monkeypatch):
    tables_chamadas_longo = []

    class FakePage:
        def __init__(self, idx: int, tracker: list[int], texto: str):
            self.idx = idx
            self.tracker = tracker
            self.texto = texto
            self.flushed = False

        def extract_text(self):
            return self.texto

        def extract_tables(self):
            self.tracker.append(self.idx)
            if self.idx == 35:
                return [[["Etapa", "Data"], ["Inscrições", "20/12/2026"]]]
            return []

        def flush_cache(self):
            self.flushed = True

    def _texto_longo(i: int) -> str:
        if i == 1:
            return "EDITAL DPG Nº 10/2026 - DISPOSIÇÕES INICIAIS"
        if i == 35:
            return "ANEXO I - CRONOGRAMA FINAL\nInscrições até 20/12/2026"
        return f"Página intermediária {i} com normas gerais."

    fake_pages = [FakePage(i, tables_chamadas_longo, _texto_longo(i)) for i in range(1, 36)]
    monkeypatch.setattr(
        pdf_mod.pdfplumber,
        "open",
        lambda stream: nullcontext(SimpleNamespace(pages=fake_pages)),
    )

    doc = pdf_mod.extract_pdf_from_bytes(b"%PDF-1.4 fake", source_name="longo.pdf")

    assert doc.num_pages == 35
    assert len(doc.pages) == 30
    assert "DISPOSIÇÕES INICIAIS" in doc.full_text
    assert "CRONOGRAMA FINAL" in doc.full_text
    assert len(doc.tables) == 1
    assert tables_chamadas_longo == [35]
    assert sum(1 for p in fake_pages if p.flushed) == 30
    assert fake_pages[24].flushed is False  # página 25 pulada no miolo (preserva head+tail)
    assert fake_pages[34].flushed is True   # página 35 processada e liberada

    # PDF curto (<= 5 páginas) sem palavras-chave ainda chama extract_tables() em todas as páginas
    tables_chamadas_curto = []
    curto_pages = [
        FakePage(i, tables_chamadas_curto, f"Texto genérico da página {i}.")
        for i in range(1, 4)
    ]
    monkeypatch.setattr(
        pdf_mod.pdfplumber,
        "open",
        lambda stream: nullcontext(SimpleNamespace(pages=curto_pages)),
    )
    doc_curto = pdf_mod.extract_pdf_from_bytes(b"%PDF-1.4 curto", source_name="curto.pdf")
    assert doc_curto.num_pages == 3
    assert tables_chamadas_curto == [1, 2, 3]
    assert all(p.flushed for p in curto_pages)


def test_download_pdf_rejeita_arquivo_acima_do_limite(monkeypatch):
    assert pdf_mod.DEFAULT_MAX_PDF_BYTES == 15 * 1024 * 1024

    mock_resp_header = MagicMock()
    mock_resp_header.headers = httpx.Headers({"content-length": str(20 * 1024 * 1024)})
    mock_resp_header.content = b"%PDF"
    mock_resp_header.raise_for_status.return_value = None

    monkeypatch.setattr(pdf_mod.httpx, "get", lambda *args, **kwargs: mock_resp_header)
    with pytest.raises(pdf_mod.PDFDownloadError, match="excede o limite"):
        pdf_mod.download_pdf("https://deg.unb.br/grande.pdf", max_bytes=1024)

    mock_resp_body = MagicMock()
    mock_resp_body.headers = httpx.Headers({})
    mock_resp_body.content = b"x" * 2048
    mock_resp_body.raise_for_status.return_value = None

    monkeypatch.setattr(pdf_mod.httpx, "get", lambda *args, **kwargs: mock_resp_body)
    with pytest.raises(pdf_mod.PDFDownloadError, match="excede o limite"):
        pdf_mod.download_pdf("https://deg.unb.br/grande2.pdf", max_bytes=1024)


def test_coleta_editais_protegida_por_chave_admin_e_lock_concorrente(monkeypatch, client):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "segredo-super-admin")

    resp_sem_chave = client.post("/api/v1/editais/sync")
    assert resp_sem_chave.status_code == 403

    resp_chave_errada = client.post("/api/v1/editais/sync", headers={"X-Admin-Key": "errada"})
    assert resp_chave_errada.status_code == 403

    assert SCRAPER_SYNC_LOCK.acquire(blocking=False) is True
    try:
        resp_concorrente = client.post(
            "/api/v1/editais/sync",
            headers={"X-Admin-Key": "segredo-super-admin"},
        )
        assert resp_concorrente.status_code == 409
        assert "andamento" in resp_concorrente.json()["detail"]

        resultado_scheduler = executar_ciclo_scraping()
        assert resultado_scheduler == {"status": "skipped", "motivo": "coleta_em_andamento"}
    finally:
        SCRAPER_SYNC_LOCK.release()

    with patch("app.modules.scraper.service.sync_orgaos_editais", return_value={"status": "success"}) as mock_sync:
        resp_ok = client.post(
            "/api/v1/editais/sync",
            headers={"X-Admin-Key": "segredo-super-admin"},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"status": "success"}
        mock_sync.assert_called_once()


def test_argon2id_perfil_low_memory_e_rehash_transparente_no_login():
    novo_hash = get_password_hash("SenhaForte123!")
    assert "m=19456,t=2,p=1" in novo_hash

    legacy_ctx = PasswordHash((Argon2Hasher(memory_cost=65536, time_cost=3, parallelism=1),))
    hash_antigo = legacy_ctx.hash("SenhaAntiga123!")
    assert "m=65536" in hash_antigo

    engine, session_factory = _make_sqlite_session_factory()
    db = session_factory()
    try:
        usuario = criar_usuario(db, nome="Estudante", email="aluno@unb.br", senha="temp")
        usuario.senha_hash = hash_antigo
        db.commit()

        assert autenticar_usuario(db, "aluno@unb.br", "SenhaErrada") is None
        autenticado = autenticar_usuario(db, "aluno@unb.br", "SenhaAntiga123!")
        assert autenticado is not None
        assert "m=19456,t=2,p=1" in autenticado.senha_hash
    finally:
        db.close()
        engine.dispose()


def test_editais_cache_aplica_eviccao_lru(monkeypatch):
    invalidar_cache_editais()
    assert isinstance(_EDITAIS_CACHE, OrderedDict)
    monkeypatch.setattr(settings, "EDITAIS_CACHE_MAXSIZE", 3)

    engine, session_factory = _make_sqlite_session_factory()
    db = session_factory()
    try:
        db.add(Edital(titulo="Edital Pesquisa CNPq", url_pagina="https://unb.br/e1"))
        db.commit()

        # Popula 3 chaves no cache: k1, k2, k3
        listar_editais_com_cache(db, busca="k1")
        listar_editais_com_cache(db, busca="k2")
        listar_editais_com_cache(db, busca="k3")
        assert len(_EDITAIS_CACHE) == 3

        # Reacessa k1 (torna k1 a mais recente; k2 vira a LRU)
        listar_editais_com_cache(db, busca="k1")

        # Insere k4 -> k2 deve ser despejada, mantendo k3, k1 e k4
        listar_editais_com_cache(db, busca="k4")
        assert len(_EDITAIS_CACHE) == 3
        termos_em_cache = {chave.termo_busca for chave in _EDITAIS_CACHE.keys()}
        assert termos_em_cache == {"k3", "k1", "k4"}
    finally:
        invalidar_cache_editais()
        db.close()
        engine.dispose()


def test_processor_notificacoes_resiliente_a_delecao_concorrente_e_timeout_sendgrid(monkeypatch):
    engine, session_factory = _make_sqlite_session_factory()
    db = session_factory()
    try:
        usuario = Usuario(nome="Ana", email="ana@unb.br", senha_hash="hash")
        edital = Edital(titulo="Edital PIBIC", url_pagina="https://unb.br/pibic")
        db.add_all([usuario, edital])
        db.flush()

        n1 = Notificacao(
            usuario_id=usuario.id,
            edital_id=edital.id,
            tipo=TipoNotificacao.EDITAL_ATUALIZADO,
            chave_evento="ev:1",
        )
        n2 = Notificacao(
            usuario_id=usuario.id,
            edital_id=edital.id,
            tipo=TipoNotificacao.EDITAL_ATUALIZADO,
            chave_evento="ev:2",
        )
        db.add_all([n1, n2])
        db.commit()
        n1_id, n2_id = n1.id, n2.id

        enviados = []

        def fake_enviar_email(**kwargs):
            enviados.append(kwargs["destinatario"])
            # Simula remoção concorrente de n2 durante o envio da 1ª notificação
            if len(enviados) == 1:
                sess_outro = session_factory()
                try:
                    sess_outro.query(Notificacao).filter(Notificacao.id == n2_id).delete()
                    sess_outro.commit()
                finally:
                    sess_outro.close()
            return True

        monkeypatch.setattr("app.modules.notificacoes.processor.enviar_email", fake_enviar_email)

        resultado = processar_notificacoes_pendentes(
            db,
            api_key="SG.test-key",
            remetente="fiquedeolho@unb.br",
            backoff_seconds=0,
        )

        assert resultado == {"enviadas": 2, "falhas": 0}
        assert db.get(Notificacao, n1_id).status == StatusNotificacao.ENVIADA
        assert db.get(Notificacao, n2_id) is None

        # Verifica configuração do timeout interno no cliente SendGrid
        instancias = []

        class FakeSendGrid:
            def __init__(self, api_key):
                self.client = SimpleNamespace(timeout=None)
                instancias.append(self)

            def send(self, mensagem):
                return SimpleNamespace(status_code=202)

        monkeypatch.setattr("app.modules.notificacoes.email_service.SendGridAPIClient", FakeSendGrid)
        assert enviar_email(
            destinatario="ana@unb.br",
            assunto="Teste",
            html="<p>Oi</p>",
            api_key="SG.key",
            remetente="fiquedeolho@unb.br",
        ) is True
        assert instancias[0].client.timeout == SENDGRID_TIMEOUT_SECONDS
    finally:
        db.close()
        engine.dispose()
