def test_health_check_returns_200(client):
    """Verifica se o endpoint /health responde com HTTP 200 e status healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_list_editais_initial_endpoint(client):
    """Verifica se o endpoint inicial de listagem de editais responde corretamente."""
    response = client.get("/api/v1/editais/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["status"] == "aberto"


def test_get_edital_by_id(client):
    response = client.get("/api/v1/editais/1")

    assert response.status_code == 200
    assert response.json()["id"] == "1"


def test_get_missing_edital_returns_404(client):
    response = client.get("/api/v1/editais/inexistente")

    assert response.status_code == 404
