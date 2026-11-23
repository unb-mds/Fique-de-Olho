"""Backfill idempotente de títulos vagos, resumos genéricos e metadados/datas ausentes.

Issues #77, #106, #121, #125 e #129.

Reprocessa editais já persistidos usando ``texto_extraido``, ``assunto``, ``orgao_emissor``
e ``url_pdf`` salvos no banco — sem baixar PDFs novamente. Por padrão roda em modo
*dry-run* (apenas exibe as mudanças); use ``--apply`` para gravar.

Uso (dentro de ``Back/``):
    python -m app.modules.scraper.backfill_titles_summaries               # dry-run
    python -m app.modules.scraper.backfill_titles_summaries --apply       # grava
    python -m app.modules.scraper.backfill_titles_summaries --orgao CEAD --limit 50 --no-llm
    python -m app.modules.scraper.backfill_titles_summaries --apply --sleep 4.0
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Edital, SessionLocal
from app.modules.scraper.parser import is_vague_title, parse_edital_metadados
from app.modules.scraper.summarizer import (
    enrich_edital_with_llm,
    is_clipped_summary,
    is_generic_summary,
    is_weak_heuristic_summary,
)

logger = logging.getLogger(__name__)


@dataclass
class BackfillChange:
    """Mudança proposta (ou aplicada) para um edital."""

    edital_id: int
    titulo_antes: str
    titulo_depois: str
    resumo_antes: Optional[str]
    resumo_depois: Optional[str]
    inicio_inscricao_antes: Optional[date] = None
    inicio_inscricao_depois: Optional[date] = None
    fim_inscricao_antes: Optional[date] = None
    fim_inscricao_depois: Optional[date] = None


def _para_data(valor: Optional[date | datetime]) -> Optional[date]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def _resumo_precisa_upgrade(edital: Edital) -> bool:
    """True quando o resumo é genérico, cortado ou recorte bruto da Camada 1 elegível a Gemini."""
    if is_generic_summary(edital.resumo, edital.titulo) or is_clipped_summary(edital.resumo):
        return True
    if settings.GEMINI_API_KEY and is_weak_heuristic_summary(edital.resumo, edital.texto_extraido):
        return True
    return False


def precisa_backfill(edital: Edital) -> bool:
    """Edital com título vago, resumo genérico/fraco ou datas ausentes com texto extraído."""
    precisa_texto = is_vague_title(edital.titulo) or _resumo_precisa_upgrade(edital)
    precisa_datas = bool(
        edital.texto_extraido
        and edital.texto_extraido.strip()
        and (edital.inicio_inscricao is None or edital.fim_inscricao is None)
    )
    return precisa_texto or precisa_datas


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
    sleep_seconds: float = 0.0,
) -> List[BackfillChange]:
    """Calcula (e opcionalmente aplica) correções de título, resumo e datas/metadados. Idempotente."""
    mudancas: List[BackfillChange] = []
    for edital in _candidatos(db, orgao):
        if limit is not None and len(mudancas) >= limit:
            break
        if not precisa_backfill(edital):
            continue

        ini_novo = _para_data(edital.inicio_inscricao)
        fim_novo = _para_data(edital.fim_inscricao)
        vagas_novo = edital.vagas
        bolsa_novo = edital.valor_bolsa

        # 1. Camada 1 local a partir do texto_extraido já persistido
        if edital.texto_extraido and (ini_novo is None or fim_novo is None or vagas_novo is None or bolsa_novo is None):
            dt_pub = edital.data_publicacao
            dt_pub_utc = (
                datetime(dt_pub.year, dt_pub.month, dt_pub.day, tzinfo=timezone.utc)
                if dt_pub is not None
                else None
            )
            ano_ref = dt_pub.year if dt_pub is not None else None
            parsed = parse_edital_metadados(
                edital.texto_extraido,
                ano_referencia=ano_ref,
                data_publicacao=dt_pub_utc,
            )
            p_ini = _para_data(parsed.inicio_inscricao)
            p_fim = _para_data(parsed.fim_inscricao)
            if ini_novo is None and p_ini is not None and (fim_novo is None or p_ini <= fim_novo):
                ini_novo = p_ini
            if fim_novo is None and p_fim is not None and (ini_novo is None or ini_novo <= p_fim):
                fim_novo = p_fim
            if vagas_novo is None and parsed.vagas is not None:
                vagas_novo = parsed.vagas
            if bolsa_novo is None and parsed.valor_bolsa is not None:
                bolsa_novo = Decimal(str(round(parsed.valor_bolsa, 2)))

        # 2. Camada 2 unificada (título + resumo + metadados ainda ausentes em no máximo 1 chamada)
        precisa_resumo = _resumo_precisa_upgrade(edital)
        resumo_atual = None if precisa_resumo else edital.resumo
        faltam_metadados = bool(edital.texto_extraido and (ini_novo is None or fim_novo is None))
        chamou_llm = bool(
            (edital.texto_extraido or edital.assunto)
            and (is_vague_title(edital.titulo) or precisa_resumo or faltam_metadados)
        )
        llm_res = enrich_edital_with_llm(
            titulo=edital.titulo,
            texto_extraido=edital.texto_extraido,
            assunto=edital.assunto,
            orgao_emissor=edital.orgao_emissor,
            url_pdf=edital.url_pdf,
            resumo_atual=resumo_atual,
            pedir_metadados=faltam_metadados,
        )
        if sleep_seconds > 0 and settings.GEMINI_API_KEY and chamou_llm:
            time.sleep(sleep_seconds)

        titulo_novo = llm_res.get("titulo") or edital.titulo
        resumo_novo = llm_res.get("resumo") or edital.resumo
        if faltam_metadados:
            l_ini = _para_data(llm_res.get("inicio_inscricao"))
            l_fim = _para_data(llm_res.get("fim_inscricao"))
            if ini_novo is None and l_ini is not None and (fim_novo is None or l_ini <= fim_novo):
                ini_novo = l_ini
            if fim_novo is None and l_fim is not None and (ini_novo is None or ini_novo <= l_fim):
                fim_novo = l_fim
            if vagas_novo is None and llm_res.get("vagas") is not None:
                vagas_novo = llm_res["vagas"]
            if bolsa_novo is None and llm_res.get("valor_bolsa") is not None:
                bolsa_novo = Decimal(str(round(float(llm_res["valor_bolsa"]), 2)))

        if ini_novo and fim_novo and ini_novo > fim_novo:
            ini_novo = _para_data(edital.inicio_inscricao)

        alterou = (
            titulo_novo != edital.titulo
            or resumo_novo != edital.resumo
            or ini_novo != _para_data(edital.inicio_inscricao)
            or fim_novo != _para_data(edital.fim_inscricao)
            or vagas_novo != edital.vagas
            or bolsa_novo != edital.valor_bolsa
        )
        if not alterou:
            continue

        mudancas.append(
            BackfillChange(
                edital_id=edital.id,
                titulo_antes=edital.titulo,
                titulo_depois=titulo_novo,
                resumo_antes=edital.resumo,
                resumo_depois=resumo_novo,
                inicio_inscricao_antes=_para_data(edital.inicio_inscricao),
                inicio_inscricao_depois=ini_novo,
                fim_inscricao_antes=_para_data(edital.fim_inscricao),
                fim_inscricao_depois=fim_novo,
            )
        )
        if apply:
            edital.titulo = titulo_novo
            edital.resumo = resumo_novo
            edital.inicio_inscricao = ini_novo
            edital.fim_inscricao = fim_novo
            edital.vagas = vagas_novo
            edital.valor_bolsa = bolsa_novo

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
        if m.inicio_inscricao_antes != m.inicio_inscricao_depois or m.fim_inscricao_antes != m.fim_inscricao_depois:
            print(
                f"  inscrição: {m.inicio_inscricao_antes}..{m.fim_inscricao_antes} "
                f"-> {m.inicio_inscricao_depois}..{m.fim_inscricao_depois}"
            )
    print(f"\nTotal: {len(mudancas)} edital(is) {'atualizado(s)' if apply else 'com mudanças propostas'}.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Grava as mudanças (padrão: dry-run).")
    parser.add_argument("--orgao", help="Restringe a um órgão emissor (ex.: CEAD, DEG).")
    parser.add_argument("--limit", type=int, help="Número máximo de editais alterados.")
    parser.add_argument("--no-llm", action="store_true", help="Usa apenas a heurística local (Camada 1).")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Intervalo em segundos entre chamadas ao LLM no backfill (ex.: 4.0 para Free Tier).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    if args.no_llm:
        settings.GEMINI_API_KEY = ""

    with SessionLocal() as session:
        mudancas = run_backfill(
            session,
            apply=args.apply,
            orgao=args.orgao,
            limit=args.limit,
            sleep_seconds=args.sleep,
        )
    _imprimir(mudancas, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
