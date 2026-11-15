import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
# Testes nunca devem chamar a Gemini API real (Issues #77/#106); os testes da Camada 2 usam mocks.
os.environ["GEMINI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    """Fixture que fornece um TestClient para executar requisições HTTP nos testes."""
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
