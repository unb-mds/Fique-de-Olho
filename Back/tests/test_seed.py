from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, TipoDocumento
from seed import SEED_EDITAIS, seed_editais


def test_seed_is_idempotent_and_covers_required_statuses_and_documents():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    try:
        with SessionLocal.begin() as session:
            seed_editais(session)

        with SessionLocal.begin() as session:
            seed_editais(session)
            first_counts = (
                session.scalar(select(func.count()).select_from(Edital)),
                session.scalar(select(func.count()).select_from(EditalDocumento)),
            )
            second_counts = (
                session.scalar(select(func.count()).select_from(Edital)),
                session.scalar(select(func.count()).select_from(EditalDocumento)),
            )

            assert second_counts == first_counts
            assert first_counts[0] == len(SEED_EDITAIS)
            assert 5 <= first_counts[0] <= 10
            assert set(session.scalars(select(Edital.status))) == {
                StatusEdital.ABERTO,
                StatusEdital.ENCERRADO,
            }
            assert {
                TipoDocumento.ORIGINAL,
                TipoDocumento.RESULTADO_PROVISORIO,
                TipoDocumento.RESULTADO_FINAL,
            }.issubset(set(session.scalars(select(EditalDocumento.tipo_documento))))

            edital_original = session.scalar(
                select(Edital).where(
                    Edital.url_pagina
                    == "https://editais.example/unb/monitoria-2026-01"
                )
            )
            assert edital_original is not None
            assert {documento.tipo_documento for documento in edital_original.documentos} == {
                TipoDocumento.ORIGINAL
            }
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()