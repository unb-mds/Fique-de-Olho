"""Populate the database with deterministic sample editais for local development."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import (
    Edital,
    EditalDocumento,
    SessionLocal,
    StatusEdital,
    TipoDocumento,
)


@dataclass(frozen=True)
class SeedDocumento:
    url_pdf: str
    tipo_documento: TipoDocumento


@dataclass(frozen=True)
class SeedEdital:
    titulo: str
    url_pagina: str
    campus: str
    tipo: str
    data_publicacao: datetime
    status: StatusEdital
    documentos: tuple[SeedDocumento, ...]


SEED_EDITAIS = (
    SeedEdital(
        titulo="Edital de Monitoria DEG 01/2026",
        url_pagina="https://editais.example/unb/monitoria-2026-01",
        campus="Darcy Ribeiro",
        tipo="Monitoria",
        data_publicacao=datetime(2026, 2, 2, tzinfo=timezone.utc),
        status=StatusEdital.ABERTO,
        documentos=(
            SeedDocumento(
                "https://editais.example/unb/monitoria-2026-01/original.pdf",
                TipoDocumento.ORIGINAL,
            ),
        ),
    ),
    SeedEdital(
        titulo="Edital PIBIC 2026",
        url_pagina="https://editais.example/unb/pibic-2026",
        campus="Darcy Ribeiro",
        tipo="Iniciação científica",
        data_publicacao=datetime(2026, 3, 10, tzinfo=timezone.utc),
        status=StatusEdital.ABERTO,
        documentos=(
            SeedDocumento(
                "https://editais.example/unb/pibic-2026/original.pdf",
                TipoDocumento.ORIGINAL,
            ),
            SeedDocumento(
                "https://editais.example/unb/pibic-2026/resultado-provisorio.pdf",
                TipoDocumento.RESULTADO_PROVISORIO,
            ),
        ),
    ),
    SeedEdital(
        titulo="Edital de Auxílio Socioeconômico 2026",
        url_pagina="https://editais.example/unb/auxilio-socioeconomico-2026",
        campus="Todos os campi",
        tipo="Assistência estudantil",
        data_publicacao=datetime(2026, 1, 20, tzinfo=timezone.utc),
        status=StatusEdital.ENCERRADO,
        documentos=(
            SeedDocumento(
                "https://editais.example/unb/auxilio-socioeconomico-2026/original.pdf",
                TipoDocumento.ORIGINAL,
            ),
            SeedDocumento(
                "https://editais.example/unb/auxilio-socioeconomico-2026/resultado-final.pdf",
                TipoDocumento.RESULTADO_FINAL,
            ),
        ),
    ),
    SeedEdital(
        titulo="Edital de Mobilidade Acadêmica 2026",
        url_pagina="https://editais.example/unb/mobilidade-2026",
        campus="Planaltina",
        tipo="Mobilidade acadêmica",
        data_publicacao=datetime(2026, 4, 5, tzinfo=timezone.utc),
        status=StatusEdital.ABERTO,
        documentos=(
            SeedDocumento(
                "https://editais.example/unb/mobilidade-2026/original.pdf",
                TipoDocumento.ORIGINAL,
            ),
            SeedDocumento(
                "https://editais.example/unb/mobilidade-2026/retificacao.pdf",
                TipoDocumento.RETIFICACAO,
            ),
        ),
    ),
    SeedEdital(
        titulo="Edital de Seleção de Bolsistas de Extensão 2026",
        url_pagina="https://editais.example/unb/extensao-bolsistas-2026",
        campus="Gama",
        tipo="Extensão",
        data_publicacao=datetime(2026, 2, 18, tzinfo=timezone.utc),
        status=StatusEdital.ENCERRADO,
        documentos=(
            SeedDocumento(
                "https://editais.example/unb/extensao-bolsistas-2026/original.pdf",
                TipoDocumento.ORIGINAL,
            ),
            SeedDocumento(
                "https://editais.example/unb/extensao-bolsistas-2026/resultado-final.pdf",
                TipoDocumento.RESULTADO_FINAL,
            ),
        ),
    ),
    SeedEdital(
        titulo="Edital de Seleção para o Programa de Educação Tutorial 2026",
        url_pagina="https://editais.example/unb/pet-2026",
        campus="Ceilândia",
        tipo="Programa de Educação Tutorial",
        data_publicacao=datetime(2026, 3, 1, tzinfo=timezone.utc),
        status=StatusEdital.ENCERRADO,
        documentos=(
            SeedDocumento(
                "https://editais.example/unb/pet-2026/original.pdf",
                TipoDocumento.ORIGINAL,
            ),
            SeedDocumento(
                "https://editais.example/unb/pet-2026/resultado-provisorio.pdf",
                TipoDocumento.RESULTADO_PROVISORIO,
            ),
        ),
    ),
)


def seed_editais(session: Session) -> None:
    for seed_edital in SEED_EDITAIS:
        edital = session.scalar(
            select(Edital).where(Edital.url_pagina == seed_edital.url_pagina)
        )
        if edital is None:
            edital = Edital(
                titulo=seed_edital.titulo,
                url_pagina=seed_edital.url_pagina,
                campus=seed_edital.campus,
                tipo=seed_edital.tipo,
                data_publicacao=seed_edital.data_publicacao,
                status=seed_edital.status,
            )
            session.add(edital)
            session.flush()

        existing_documents = set(
            session.execute(
                select(EditalDocumento.url_pdf, EditalDocumento.tipo_documento).where(
                    EditalDocumento.edital_id == edital.id
                )
            ).all()
        )
        for seed_documento in seed_edital.documentos:
            document_key = (
                seed_documento.url_pdf,
                seed_documento.tipo_documento,
            )
            if document_key not in existing_documents:
                session.add(
                    EditalDocumento(
                        edital_id=edital.id,
                        url_pdf=seed_documento.url_pdf,
                        tipo_documento=seed_documento.tipo_documento,
                    )
                )
                existing_documents.add(document_key)

    session.flush()


def main() -> None:
    with SessionLocal.begin() as session:
        seed_editais(session)
    print(f"Seed concluído: {len(SEED_EDITAIS)} editais de exemplo disponíveis.")


if __name__ == "__main__":
    main()