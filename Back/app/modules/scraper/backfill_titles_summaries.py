"""Backfill idempotente de títulos vagos e resumos genéricos/ausentes (Issues #77 e #106).

Reprocessa editais já persistidos usando ``texto_extraido``, ``assunto``, ``orgao_emissor``
e ``url_pdf`` salvos no banco — sem baixar PDFs novamente. Por padrão roda em modo
*dry-run* (apenas exibe as mudanças); use ``--apply`` para gravar.

Uso (dentro de ``Back/``):
    python -m app.modules.scraper.backfill_titles_summaries               # dry-run
    python -m app.modules.scraper.backfill_titles_summaries --apply       # grava
    python -m app.modules.scraper.backfill_titles_summaries --orgao CEAD --limit 50 --no-llm
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Edital, SessionLocal
from app.modules.scraper.parser import is_vague_title
from app.modules.scraper.summarizer import enrich_title_and_summary, is_generic_summary

logger = logging.getLogger(__name__)


@dataclass
class BackfillChange:
    """Mudança proposta (ou aplicada) para um edital."""

    edital_id: int
    titulo_antes: str
    titulo_depois: str
    resumo_antes: Optional[str]
    resumo_depois: Optional[str]


def precisa_backfill(edital: Edital) -> bool:
    """Edital com título vago ou resumo ausente/genérico/igual ao título."""
    return is_vague_title(edital.titulo) or is_generic_summary(edital.resumo, edital.titulo)


def _candidatos(db: Session, orgao: Optional[str]) -> Iterable[Edital]:
    query = db.query(Edital).order_by(Edital.id)
    if orgao:
        query = query.filter(Edital.orgao_emissor == orgao.upper().strip())
    return query.yield_per(200)


def run_backfill(
    db: Session,
    apply: bool = False,
    orgao: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[BackfillChange]:
    """Calcula (e opcionalmente aplica) as correções de título/resumo. Idempotente."""
    mudancas: List[BackfillChange] = []
    for edital in _candidatos(db, orgao):
        if limit is not None and len(mudancas) >= limit:
            break
        if not precisa_backfill(edital):
            continue

        resumo_atual = None if is_generic_summary(edital.resumo, edital.titulo) else edital.resumo
        titulo_novo, resumo_novo = enrich_title_and_summary(
            titulo=edital.titulo,
            texto_extraido=edital.texto_extraido,
            assunto=edital.assunto,
            orgao_emissor=edital.orgao_emissor,
            url_pdf=edital.url_pdf,
            resumo_atual=resumo_atual or edital.resumo,
        )
        resumo_novo = resumo_novo or edital.resumo
        if titulo_novo == edital.titulo and resumo_novo == edital.resumo:
            continue

        mudancas.append(
            BackfillChange(
                edital_id=edital.id,
                titulo_antes=edital.titulo,
                titulo_depois=titulo_novo,
                resumo_antes=edital.resumo,
                resumo_depois=resumo_novo,
            )
        )
        if apply:
            edital.titulo = titulo_novo
            edital.resumo = resumo_novo

    if apply and mudancas:
        db.commit()
    return mudancas


def _imprimir(mudancas: List[BackfillChange], apply: bool) -> None:
    modo = "APLICADO" if apply else "DRY-RUN"
    for m in mudancas:
        print(f"[{modo}] Edital #{m.edital_id}")
        if m.titulo_antes != m.titulo_depois:
            print(f"  título: {m.titulo_antes!r}\n       -> {m.titulo_depois!r}")
        if m.resumo_antes != m.resumo_depois:
            print(f"  resumo: {m.resumo_antes!r}\n       -> {m.resumo_depois!r}")
    print(f"\nTotal: {len(mudancas)} edital(is) {'atualizado(s)' if apply else 'com mudanças propostas'}.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Grava as mudanças (padrão: dry-run).")
    parser.add_argument("--orgao", help="Restringe a um órgão emissor (ex.: CEAD, DEG).")
    parser.add_argument("--limit", type=int, help="Número máximo de editais alterados.")
    parser.add_argument("--no-llm", action="store_true", help="Usa apenas a heurística local (Camada 1).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    if args.no_llm:
        settings.GEMINI_API_KEY = ""

    with SessionLocal() as session:
        mudancas = run_backfill(session, apply=args.apply, orgao=args.orgao, limit=args.limit)
    _imprimir(mudancas, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
