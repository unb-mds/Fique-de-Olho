"""Testes automatizados para endpoints integrados ao PostgreSQL de editais."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Campus, Edital, EditalDocumento, StatusEdital, TipoDocumento, TipoEdital, get_db
from app.main import app
from app.modules.editais.service import (
    _EDITAIS_CACHE,
    EDITAIS_CACHE_TTL_SECONDS,
    invalidar_cache_editais,
    list_editais_com_filtros,
)
from app.modules.scraper.scheduler import executar_ciclo_scraping


@pytest.fixture
def sync_client():
    """Fornece um banco isolado para testar a sincronização de editais."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = testing_session_local()
    session.add_all(
        [
            Campus(nome="Darcy Ribeiro"),
            TipoEdital(nome="Extensões"),
        ]
    )
    session.commit()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


def test_list_editais_with_status_filter(client):
    """Testa filtro por status 'aberto'."""
    response = client.get("/api/v1/editais/?status=aberto")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for edital in data:
        assert edital["status"] == "aberto"


def test_list_editais_with_search_query(client):
    """Testa busca textual no endpoint de editais."""
    response = client.get("/api/v1/editais/?busca=Monitoria")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any("Monitoria" in e["titulo"] or "Monitoria" in (e.get("resumo") or "") for e in data)


def test_get_edital_detail_success(client):
    """Testa busca de edital por ID existente."""
    list_resp = client.get("/api/v1/editais/")
    assert list_resp.status_code == 200
    editais = list_resp.json()
    assert len(editais) > 0
    first_id = editais[0]["id"]

    detail_resp = client.get(f"/api/v1/editais/{first_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["id"] == first_id
    assert "titulo" in data
    assert "url_pdf" in data
    assert "status" in data


def test_get_edital_detail_not_found(client):
    """Testa busca de edital com ID inexistente (deve retornar 404)."""
    response = client.get("/api/v1/editais/999999")
    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"]


def test_direct_editais_route_compatibility(client):
    """Testa compatibilidade da rota /editais/:id usada pelo Frontend."""
    list_resp = client.get("/editais/")
    assert list_resp.status_code == 200
    editais = list_resp.json()
    assert len(editais) > 0
    first_id = editais[0]["id"]

    detail_resp = client.get(f"/editais/{first_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == first_id


def test_sync_editais_service(sync_client):
    """Testa endpoint de sincronização com dados do portal simulados."""
    fake_scraped = [
        {
            "titulo": "Edital Teste Mock Coleta 2026",
            "link": "https://deg.unb.br/editais/edital-teste-mock-2026.pdf",
            "data_publicacao": "01 de outubro de 2026",
        }
    ]
    with patch("app.modules.scraper.service.fetch_editais", return_value=fake_scraped):
        response = sync_client.post("/api/v1/editais/sync?max_itens=5")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "coleta_id" in data


def test_list_editais_avoids_n_plus_one_and_defers_texto_extraido():
    """Garante que a listagem carrega relacionamentos em lote (sem N+1) e adia texto_extraido."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = testing_session_local()
    campus = Campus(nome="Darcy Ribeiro")
    tipo = TipoEdital(nome="Extensões")
    session.add_all([campus, tipo])
    session.flush()

    for idx in range(15):
        edital = Edital(
            identificador_origem=f"edital-n1-{idx}",
            titulo=f"Edital Performance {idx}",
            url_pagina=f"https://deg.unb.br/edital-{idx}",
            url_pdf=f"https://deg.unb.br/edital-{idx}.pdf",
            texto_extraido="Conteudo extenso do PDF " * 200,
            status=StatusEdital.ABERTO,
            status_processamento="processado",
        )
        edital.campi.append(campus)
        edital.tipos.append(tipo)
        edital.documentos.append(
            EditalDocumento(
                url_pdf=f"https://deg.unb.br/edital-{idx}-anexo.pdf",
                tipo_documento=TipoDocumento.ORIGINAL,
            )
        )
        session.add(edital)
    session.commit()
    session.close()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    select_queries = []

    def count_queries(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            select_queries.append(statement)

    event.listen(engine, "before_cursor_execute", count_queries)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            # Verifica que texto_extraido fica adiado (deferred) na consulta de listagem
            check_db = testing_session_local()
            try:
                editais_orm = list_editais_com_filtros(check_db)
                assert len(editais_orm) == 15
                assert "texto_extraido" in inspect(editais_orm[0]).unloaded
            finally:
                check_db.close()

            select_queries.clear()
            resp = test_client.get(
                "/api/v1/editais/",
                headers={"Accept-Encoding": "gzip"},
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert len(payload) == 15
            assert len(payload[0]["documentos"]) == 1
            assert "texto_extraido" not in payload[0]
            # 4 SELECTs esperados: editais + documentos + tipos + campi (sem N+1 por edital)
            assert len(select_queries) <= 5

            # Na rota de detalhe, texto_extraido continua sendo retornado normalmente
            first_id = payload[0]["id"]
            detail_resp = test_client.get(f"/api/v1/editais/{first_id}")
            assert detail_resp.status_code == 200
            assert "Conteudo extenso do PDF" in detail_resp.json()["texto_extraido"]
    finally:
        event.remove(engine, "before_cursor_execute", count_queries)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_list_editais_cache_hit_stale_while_revalidate_and_sync_invalidation(sync_client):
    """Valida hit de cache em memória, revalidação Stale-While-Revalidate e invalidação após coleta."""
    invalidar_cache_editais()

    # Popula 1 edital inicial via /sync
    initial_scraped = [
        {
            "titulo": "Edital Cache Inicial 2026",
            "link": "https://deg.unb.br/editais/edital-cache-inicial-2026.pdf",
            "data_publicacao": "01 de outubro de 2026",
        }
    ]
    with patch("app.modules.scraper.service.fetch_editais", return_value=initial_scraped):
        sync_resp = sync_client.post("/api/v1/editais/sync?max_itens=5")
        assert sync_resp.status_code == 200

    # 1ª chamada: Cache miss -> consulta o banco e popula o cache
    resp_1 = sync_client.get("/api/v1/editais/")
    assert resp_1.status_code == 200
    data_1 = resp_1.json()
    assert len(data_1) == 1
    assert data_1[0]["titulo"] == "Edital Cache Inicial 2026"

    # 2ª chamada dentro do TTL: Cache hit -> não deve chamar list_editais_com_filtros
    with patch("app.modules.editais.service.list_editais_com_filtros") as mock_list:
        resp_2 = sync_client.get("/api/v1/editais/")
        assert resp_2.status_code == 200
        assert resp_2.json() == data_1
        mock_list.assert_not_called()

    # Insere um 2º edital diretamente no banco sem invalidar o cache e expira o TTL
    db_gen = app.dependency_overrides[get_db]()
    direct_db = next(db_gen)
    try:
        direct_db.add(
            Edital(
                identificador_origem="edital-swr-bg-2026",
                titulo="Edital Revalidado Background 2026",
                url_pagina="https://deg.unb.br/editais/edital-swr-bg-2026",
                url_pdf="https://deg.unb.br/editais/edital-swr-bg-2026.pdf",
                status=StatusEdital.ABERTO,
                status_processamento="processado",
            )
        )
        direct_db.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    for entrada in _EDITAIS_CACHE.values():
        entrada.timestamp -= EDITAIS_CACHE_TTL_SECONDS + 10

    # Chamada com cache expirado (SWR): devolve dado antigo imediatamente e revalida em background
    resp_stale = sync_client.get("/api/v1/editais/")
    assert resp_stale.status_code == 200
    assert resp_stale.json() == data_1

    # Após a BackgroundTask concluir, o cache já contém o 2º edital sem precisar de nova query
    with patch("app.modules.editais.service.list_editais_com_filtros") as mock_list_after_swr:
        resp_refreshed = sync_client.get("/api/v1/editais/")
        assert resp_refreshed.status_code == 200
        titulos_swr = [item["titulo"] for item in resp_refreshed.json()]
        assert "Edital Revalidado Background 2026" in titulos_swr
        mock_list_after_swr.assert_not_called()

    # Coleta via /sync invalida o cache imediatamente
    updated_scraped = initial_scraped + [
        {
            "titulo": "Edital Novo Pos Coleta 2026",
            "link": "https://deg.unb.br/editais/edital-novo-pos-sync-2026.pdf",
            "data_publicacao": "05 de outubro de 2026",
        }
    ]
    with patch("app.modules.scraper.service.fetch_editais", return_value=updated_scraped):
        sync_resp_2 = sync_client.post("/api/v1/editais/sync?max_itens=5")
        assert sync_resp_2.status_code == 200

    resp_after_sync = sync_client.get("/api/v1/editais/")
    assert resp_after_sync.status_code == 200
    titulos = [item["titulo"] for item in resp_after_sync.json()]
    assert "Edital Novo Pos Coleta 2026" in titulos

    # Ciclo do scheduler também invalida o cache em memória
    assert len(_EDITAIS_CACHE) > 0
    with patch("app.modules.scraper.scheduler.sync_all_portais", return_value={"status": "success"}):
        executar_ciclo_scraping()
    assert len(_EDITAIS_CACHE) == 0


