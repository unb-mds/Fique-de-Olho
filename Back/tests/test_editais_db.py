"""Testes automatizados para endpoints integrados ao PostgreSQL de editais."""

from unittest.mock import patch


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


def test_sync_editais_service(client):
    """Testa endpoint de sincronização com dados do portal simulados."""
    fake_scraped = [
        {
            "titulo": "Edital Teste Mock Coleta 2026",
            "link": "https://deg.unb.br/editais/edital-teste-mock-2026.pdf",
            "data_publicacao": "01 de outubro de 2026",
        }
    ]
    with patch("app.modules.scraper.service.fetch_editais", return_value=fake_scraped):
        response = client.post("/api/v1/editais/sync?max_itens=5")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "coleta_id" in data
