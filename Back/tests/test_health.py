from unittest.mock import patch


def test_health_check_returns_200(client):
    """Verifica se o endpoint /health responde com HTTP 200 e status healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["database"] == "connected"


def test_ping_endpoint_returns_awake_without_database_query(client):
    """Verifica que /ping responde HTTP 200 com {'status': 'awake'} em GET e HEAD sem tocar no banco."""
    with patch("app.main.engine.connect", side_effect=AssertionError("Nao deve consultar o banco")) as mock_connect:
        response_get = client.get("/ping")
        assert response_get.status_code == 200
        assert response_get.json() == {"status": "awake"}

        response_head = client.head("/ping")
        assert response_head.status_code == 200
        mock_connect.assert_not_called()


def test_list_editais_initial_endpoint(client):
    """Verifica se o endpoint inicial de listagem de editais responde corretamente."""
    response = client.get("/api/v1/editais/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["status"] in ("aberto", "fechado")


def test_get_edital_by_id(client):
    response = client.get("/api/v1/editais/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_get_missing_edital_returns_404(client):
    response = client.get("/api/v1/editais/inexistente")

    assert response.status_code == 404
