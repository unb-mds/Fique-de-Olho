from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, TipoDocumento, get_db
from app.main import app


@pytest.fixture
def db_session_editais():
    """Cria banco SQLite em memória com múltiplos editais para testar filtros."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Cria editais variados de diferentes anos e títulos
    e1 = Edital(
        id=1,
        titulo="Edital Monitoria DEG 01/2026",
        url_pagina="https://deg.unb.br/editais/monitoria-2026",
        campus="Darcy Ribeiro",
        tipo="monitoria",
        data_publicacao=datetime(2026, 3, 15),
        status=StatusEdital.ABERTO,
    )
    doc1 = EditalDocumento(
        id=1,
        edital_id=1,
        url_pdf="https://deg.unb.br/docs/monitoria.pdf",
        tipo_documento=TipoDocumento.ORIGINAL,
    )

    e2 = Edital(
        id=2,
        titulo="Processo Seletivo Transferência Facultativa 2025",
        url_pagina="https://deg.unb.br/editais/transferencia-2025",
        campus="FGA",
        tipo="transferencia",
        data_publicacao=datetime(2025, 6, 20),
        status=StatusEdital.ENCERRADO,
    )

    e3 = Edital(
        id=3,
        titulo="Edital de Estágio Não Obrigatório 2026",
        url_pagina="https://deg.unb.br/editais/estagio-2026",
        campus="Darcy Ribeiro",
        tipo="estagio",
        data_publicacao=datetime(2026, 8, 10),
        status=StatusEdital.ABERTO,
    )

    session.add_all([e1, doc1, e2, e3])
    session.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client_editais(db_session_editais):
    with TestClient(app) as test_client:
        yield test_client


def test_list_editais_sem_filtro_retorna_todos(client_editais):
    response = client_editais.get("/editais/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    # Verifica que o primeiro tem documento vinculado
    edital_1 = next(e for e in data if e["id"] == 1)
    assert len(edital_1["documentos"]) == 1
    assert edital_1["documentos"][0]["tipo_documento"] == "original"


def test_list_editais_filtro_por_ano(client_editais):
    # Filtra por 2025: deve retornar apenas o e2
    response = client_editais.get("/editais/?ano=2025")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2
    assert "2025" in data[0]["titulo"]

    # Filtra por 2026: deve retornar e1 e e3
    response_2026 = client_editais.get("/editais/?ano=2026")
    assert response_2026.status_code == 200
    data_2026 = response_2026.json()
    assert len(data_2026) == 2


def test_list_editais_filtro_por_busca_texto_q(client_editais):
    # Busca case-insensitive "monitoria"
    response = client_editais.get("/editais/?q=MONITORIA")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1


def test_list_editais_filtro_combinado_ano_e_busca(client_editais):
    # Busca "edital" no ano 2026: retorna e1 e e3
    response = client_editais.get("/editais/?ano=2026&q=edital")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Busca "transferência" no ano 2026: não existe em 2026
    response_vazia = client_editais.get("/editais/?ano=2026&q=transferência")
    assert response_vazia.status_code == 200
    assert response_vazia.json() == []


def test_list_editais_termo_inexistente(client_editais):
    response = client_editais.get("/editais/?q=termo_completamente_inexistente")
    assert response.status_code == 200
    assert response.json() == []


def test_list_editais_prefix_api_v1(client_editais):
    response = client_editais.get("/api/v1/editais/?ano=2025")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
