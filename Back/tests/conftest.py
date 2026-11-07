import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    """Fixture que fornece um TestClient para executar requisições HTTP nos testes."""
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
