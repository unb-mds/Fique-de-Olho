from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import database
from app.core.database import (
    Base,
    Edital,
    EditalDocumento,
    Favorito,
    StatusEdital,
    TipoDocumento,
    Usuario,
)
from app.main import app


def test_database_schema_has_required_tables_and_columns():
    table_names = set(Base.metadata.tables)

    assert {"editais", "edital_documentos", "usuarios", "favoritos"}.issubset(table_names)

    editais = Base.metadata.tables["editais"]
    assert {"titulo", "url_pagina", "campus", "tipo", "data_publicacao", "status", "created_at"}.issubset(editais.columns.keys())

    documentos = Base.metadata.tables["edital_documentos"]
    assert {"edital_id", "url_pdf", "tipo_documento", "created_at"}.issubset(documentos.columns.keys())

    usuarios = Base.metadata.tables["usuarios"]
    assert {"nome", "email", "senha_hash", "created_at"}.issubset(usuarios.columns.keys())

    favoritos = Base.metadata.tables["favoritos"]
    assert {"usuario_id", "edital_id", "created_at"}.issubset(favoritos.columns.keys())
    assert list(favoritos.primary_key.columns.keys()) == ["usuario_id", "edital_id"]


def test_database_models_can_be_created_in_sqlite_memory_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        usuario = Usuario(
            nome="Ana Souza",
            email="ana@teste.com",
            senha_hash="hash_seguro",
        )
        edital = Edital(
            titulo="Edital de Monitoria 2026",
            url_pagina="https://example.com/editais/monitoria-2026",
            campus="Darcy Ribeiro",
            tipo="monitoria",
            data_publicacao=datetime(2026, 9, 27),
            status=StatusEdital.ABERTO,
        )

        session.add_all([usuario, edital])
        session.commit()

        documento = EditalDocumento(
            edital_id=edital.id,
            url_pdf="https://example.com/documentos/monitoria.pdf",
            tipo_documento=TipoDocumento.ORIGINAL,
        )
        favorito = Favorito(usuario_id=usuario.id, edital_id=edital.id)

        session.add_all([documento, favorito])
        session.commit()

        assert session.get(Usuario, usuario.id).email == "ana@teste.com"
        assert session.get(Favorito, (usuario.id, edital.id)) is not None
        assert session.get(EditalDocumento, documento.id).tipo_documento == TipoDocumento.ORIGINAL


def test_app_startup_does_not_create_database_schema(monkeypatch):
    called = {"value": False}

    def fake_create_all(*args, **kwargs):
        called["value"] = True

    monkeypatch.setattr(database.Base.metadata, "create_all", fake_create_all)

    with TestClient(app):
        pass

    assert called["value"] is False
