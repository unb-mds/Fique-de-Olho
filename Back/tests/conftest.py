import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    """Fixture que fornece um TestClient para executar requisições HTTP nos testes."""
    with TestClient(app) as test_client:
        yield test_client
