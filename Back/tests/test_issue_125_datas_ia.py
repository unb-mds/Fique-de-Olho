"""Testes unitários e de integração da Issue #125:
- Parser de datas ampliado (horários intercalados, entre...e..., separadores . e -, default_year, mês inválido).
- Tabelas de cronograma com 3+ colunas, início/término separados e continuação entre páginas.
- Fallback textual multi-ocorrência e multilinha (ignorando taxa/cabeçalho sem data).
- Camada 2 unificada com Gemini (1 única chamada, seleção inteligente de trechos com cronograma tardio, modelo ativo).
- Retificações de prazo, reprocessamento local de legados e backfill de datas.
"""

from datetime import date, datetime, timezone
import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, Edital
from app.modules.scraper import pipeline as pipeline_mod
from app.modules.scraper import summarizer as summarizer_mod
from app.modules.scraper.backfill_titles_summaries import run_backfill
from app.modules.scraper.parser import (
    parse_cronograma_from_tables,
    parse_data_interval,
    parse_date_pt,
    parse_edital_metadados,
)
from app.modules.scraper.pdf import PDFDocumentExtraction
from app.modules.scraper.summarizer import (
    MAX_TEXTO_PROMPT_CHARS,
    enrich_edital_with_llm,
    selecionar_trechos_relevantes_prompt,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()


def _gemini_payload(obj: dict) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj, ensure_ascii=False)}]}}]}


# ---------------------------------------------------------------------------
# 1. Novos padrões de datas e parse_date_pt
# ---------------------------------------------------------------------------


def test_parse_date_pt_retorna_none_para_mes_invalido():
    assert parse_date_pt("10", "invalido", "2026") is None
    assert parse_date_pt("31", "fevereiro", "2026") is None


def test_parse_data_interval_horarios_intercalados():
    ini, fim = parse_data_interval("das 10h do dia 01/11/2026 às 18h do dia 15/11/2026")
    assert ini == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert fim == datetime(2026, 11, 15, tzinfo=timezone.utc)

    ini2, fim2 = parse_data_interval("de 01/11/2026 (08h) a 15/11/2026 (23h59)")
    assert ini2 == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert fim2 == datetime(2026, 11, 15, tzinfo=timezone.utc)


def test_parse_data_interval_entre_e_separadores_alternativos():
    ini, fim = parse_data_interval("entre os dias 10 e 20 de novembro de 2026")
    assert ini == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert fim == datetime(2026, 11, 20, tzinfo=timezone.utc)

    ini2, fim2 = parse_data_interval("entre 10/11/2026 e 20/11/2026")
    assert ini2 == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert fim2 == datetime(2026, 11, 20, tzinfo=timezone.utc)

    ini3, fim3 = parse_data_interval("10.11.2026 - 25.11.2026")
    assert ini3 == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert fim3 == datetime(2026, 11, 25, tzinfo=timezone.utc)

    ini_hifen, fim_hifen = parse_data_interval("10-11-2026 a 25-11-2026")
    assert ini_hifen == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert fim_hifen == datetime(2026, 11, 25, tzinfo=timezone.utc)

    ini4, fim4 = parse_data_interval("10/11 a 25/11", default_year=2026)
    assert ini4 == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert fim4 == datetime(2026, 11, 25, tzinfo=timezone.utc)


def test_parse_data_interval_evita_falsos_positivos_de_numeracao():
    assert parse_data_interval("Conforme subitem 3.1.10 do edital") == (None, None)
    assert parse_data_interval("Itens 3.1 a 3.4 do regulamento", default_year=2026) == (None, None)
    ini, fim = parse_data_interval("Fase 1 - 15/11/2026")
    assert ini == datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert fim == datetime(2026, 11, 15, tzinfo=timezone.utc)


def test_parse_cronograma_cabecalho_com_preposicao_de():
    tabela = [
        ["Etapa", "Data de realização"],
        ["Período de inscrições", "02/11/2026 a 18/11/2026"],
    ]
    doc = PDFDocumentExtraction(source="edital.pdf", num_pages=1, full_text="EDITAL DEG", tables=[tabela])
    meta = parse_edital_metadados(doc)
    assert meta.inicio_inscricao == datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert meta.fim_inscricao == datetime(2026, 11, 18, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 2. Tabelas multi-coluna e continuação entre páginas
# ---------------------------------------------------------------------------


def test_parse_cronograma_tabela_tres_colunas_com_item():
    tabela = [
        ["Item", "Etapa", "Período"],
        ["1", "Inscrições dos candidatos", "03/11/2026 a 18/11/2026"],
        ["2", "Resultado final", "30/11/2026"],
    ]
    doc = PDFDocumentExtraction(source="edital.pdf", num_pages=1, full_text="EDITAL DEG", tables=[tabela])
    meta = parse_edital_metadados(doc)
    assert meta.inicio_inscricao == datetime(2026, 11, 3, tzinfo=timezone.utc)
    assert meta.fim_inscricao == datetime(2026, 11, 18, tzinfo=timezone.utc)
    assert meta.data_resultado_final == datetime(2026, 11, 30, tzinfo=timezone.utc)


def test_parse_cronograma_colunas_inicio_termino_e_continuacao_pagina():
    tabela_pag1 = [
        ["Atividade", "Início", "Término"],
        ["Publicação do Edital", "01/11/2026", "01/11/2026"],
    ]
    tabela_pag2_continuacao = [
        ["Período de inscrições", "05/11/2026", "20/11/2026"],
        ["Homologação das inscrições", "22/11/2026", "22/11/2026"],
    ]
    etapas = parse_cronograma_from_tables([tabela_pag1, tabela_pag2_continuacao])
    assert len(etapas) == 3

    doc = PDFDocumentExtraction(
        source="edital.pdf",
        num_pages=2,
        full_text="EDITAL DPG",
        tables=[tabela_pag1, tabela_pag2_continuacao],
    )
    meta = parse_edital_metadados(doc)
    assert meta.inicio_inscricao == datetime(2026, 11, 5, tzinfo=timezone.utc)
    assert meta.fim_inscricao == datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert meta.data_resultado_preliminar == datetime(2026, 11, 22, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 3. Fallback textual multi-ocorrência e multilinha
# ---------------------------------------------------------------------------


def test_fallback_textual_ignora_taxa_e_cabecalho_sem_data():
    texto = (
        "EDITAL DEG Nº 12/2026\n"
        "1. DA TAXA DE INSCRIÇÃO\n"
        "1.1 Não haverá cobrança de taxa de inscrição para este processo.\n\n"
        "3. DAS INSCRIÇÕES\n"
        "3.1 Os estudantes interessados deverão realizar suas inscrições\n"
        "das 08h do dia 10/11/2026 às 23h59 do dia 24/11/2026 pelo SIGAA.\n"
    )
    meta = parse_edital_metadados(texto)
    assert meta.inicio_inscricao == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert meta.fim_inscricao == datetime(2026, 11, 24, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 4. Camada 2 (Gemini): modelo ativo, recorte com cronograma tardio e 1 chamada unificada
# ---------------------------------------------------------------------------


def test_gemini_model_padrao_esta_ativo():
    assert settings.GEMINI_MODEL != "gemini-1.5-flash"
    assert settings.GEMINI_MODEL in (
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
        "gemini-2.5-flash",
    )


def test_selecionar_trechos_preserva_cronograma_apos_6000_chars():
    cabecalho = "EDITAL DPG Nº 22/2026 - SELEÇÃO DE MESTRADO EM ZOOLOGIA.\n"
    recheio = ("Disposições gerais e normas regimentais da universidade. " * 180) + "\n"
    cronograma = (
        "ANEXO I - CRONOGRAMA DO PROCESSO SELETIVO\n"
        "Período de inscrições: 01/12/2026 a 18/12/2026.\n"
        "Valor da bolsa: R$ 2.100,00.\n"
    )
    texto_longo = cabecalho + recheio + cronograma
    assert len(cabecalho + recheio) > MAX_TEXTO_PROMPT_CHARS

    selecionado = selecionar_trechos_relevantes_prompt(texto_longo, max_chars=MAX_TEXTO_PROMPT_CHARS)
    assert len(selecionado) <= MAX_TEXTO_PROMPT_CHARS
    assert "EDITAL DPG Nº 22/2026" in selecionado
    assert "01/12/2026 a 18/12/2026" in selecionado


def test_upsert_segunda_passada_unificada_faz_apenas_uma_chamada_gemini(db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
    chamadas = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Edital DEG Nº 44/2026 - Seleção de Bolsistas",
                    "resumo": "Seleção de bolsistas de graduação para apoio acadêmico na UnB.",
                    "inicio_inscricao": "2026-11-05",
                    "fim_inscricao": "2026-11-28",
                    "valor_bolsa": 700.0,
                    "tem_bolsa": True,
                    "vagas": 10,
                    "orgao_emissor": "DEG",
                }
            ),
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(summarizer_mod, "_build_client", lambda timeout: httpx.Client(transport=transport, timeout=timeout))

    # Simula PDF cujo texto não tem datas capturáveis pelo regex da Camada 1
    fake_pdf = PDFDocumentExtraction(
        source="https://deg.unb.br/edital-44.pdf",
        num_pages=1,
        full_text="EDITAL DEG Nº 44/2026. Processo seletivo para estudantes da UnB com prazo definido pela coordenação.",
        tables=[],
    )
    monkeypatch.setattr(pipeline_mod, "extract_pdf", lambda url, timeout=15.0: fake_pdf)

    edital = pipeline_mod.upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "AQUI",
            "link": "https://deg.unb.br/editais/edital-44",
            "url_pdf": "https://deg.unb.br/edital-44.pdf",
            "resumo": "Edital publicado pelo portal DEG em 2026-11-01.",
        },
        enable_pdf_enrichment=True,
    )

    assert chamadas["n"] == 1
    assert edital.titulo == "Edital DEG Nº 44/2026 - Seleção de Bolsistas"
    assert edital.resumo == "Seleção de bolsistas de graduação para apoio acadêmico na UnB."
    assert edital.inicio_inscricao == date(2026, 11, 5)
    assert edital.fim_inscricao == date(2026, 11, 28)
    assert float(edital.valor_bolsa) == 700.0
    assert edital.vagas == 10


def test_upsert_camada_2_nao_sobrescreve_dados_validos_e_pula_quando_completo(db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
    chamadas = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "inicio_inscricao": "2026-01-01",
                    "fim_inscricao": "2026-01-02",
                    "valor_bolsa": 999.0,
                    "vagas": 99,
                }
            ),
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(summarizer_mod, "_build_client", lambda timeout: httpx.Client(transport=transport, timeout=timeout))

    # Quando Camada 1 / scraper já trazem tudo completo, Gemini nem deve ser chamado
    completo = pipeline_mod.upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital DEG Nº 50/2026 - Monitoria",
            "link": "https://deg.unb.br/editais/edital-50",
            "resumo": "Seleção de monitores remunerados para disciplinas de graduação.",
            "inicio_inscricao": "2026-11-01",
            "fim_inscricao": "2026-11-20",
            "valor_bolsa": 700.0,
            "vagas": 8,
            "campus": "Darcy Ribeiro",
            "texto_extraido": "Texto completo do edital...",
        },
        enable_pdf_enrichment=True,
    )
    assert chamadas["n"] == 0
    assert completo.fim_inscricao == date(2026, 11, 20)

    # Quando falta apenas valor_bolsa, Gemini roda mas NÃO sobrescreve datas/vagas válidas do scraper
    parcial = pipeline_mod.upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital DEG Nº 51/2026 - Iniciação Científica",
            "link": "https://deg.unb.br/editais/edital-51",
            "resumo": "Seleção de estudantes para iniciação científica na UnB.",
            "inicio_inscricao": "2026-11-02",
            "fim_inscricao": "2026-11-22",
            "vagas": 5,
            "campus": "Darcy Ribeiro",
            "texto_extraido": "Edital com bolsa paga pela fundação parceira.",
        },
        enable_pdf_enrichment=True,
    )
    assert chamadas["n"] == 1
    assert parcial.inicio_inscricao == date(2026, 11, 2)
    assert parcial.fim_inscricao == date(2026, 11, 22)
    assert parcial.vagas == 5
    assert float(parcial.valor_bolsa) == 999.0


# ---------------------------------------------------------------------------
# 5. Retificação de prazo, reprocessamento local e backfill
# ---------------------------------------------------------------------------


def test_retificacao_prorroga_fim_inscricao(db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    pdf_original = PDFDocumentExtraction(
        source="https://deg.unb.br/original.pdf",
        num_pages=1,
        full_text="EDITAL DEG Nº 10/2026\nInscrições: 01/11/2026 a 10/11/2026.",
        tables=[],
    )
    pdf_retificacao = PDFDocumentExtraction(
        source="https://deg.unb.br/retificacao-01.pdf",
        num_pages=1,
        full_text="RETIFICAÇÃO Nº 01\nFicam prorrogadas as inscrições até 25/11/2026.",
        tables=[],
    )

    def fake_extract(url, timeout=15.0):
        return pdf_retificacao if "retificacao" in url else pdf_original

    monkeypatch.setattr(pipeline_mod, "extract_pdf", fake_extract)

    edital = pipeline_mod.upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital DEG Nº 10/2026 - Monitoria",
            "link": "https://deg.unb.br/editais/10-2026",
            "url_pdf": "https://deg.unb.br/original.pdf",
        },
        documentos_data=[
            {"link": "https://deg.unb.br/original.pdf", "tipo": "original"},
            {"link": "https://deg.unb.br/retificacao-01.pdf", "tipo": "retificacao", "titulo": "Retificação 01"},
        ],
        enable_pdf_enrichment=True,
    )

    assert edital.inicio_inscricao == date(2026, 11, 1)
    assert edital.fim_inscricao == date(2026, 11, 25)


def test_backfill_preenche_datas_ausentes_de_edital_legado(db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    legado = Edital(
        titulo="Edital Monitoria DEG 15/2026",
        url_pagina="https://deg.unb.br/editais/15-2026",
        orgao_emissor="DEG",
        resumo="Seleção de monitores remunerados para disciplinas de graduação.",
        texto_extraido=(
            "EDITAL DEG Nº 15/2026\n"
            "3. DAS INSCRIÇÕES\n"
            "3.1 As inscrições estarão abertas entre os dias 12 e 26 de novembro de 2026.\n"
        ),
        inicio_inscricao=None,
        fim_inscricao=None,
    )
    db_session.add(legado)
    db_session.commit()

    dry = run_backfill(db_session, apply=False)
    assert len(dry) == 1
    assert dry[0].inicio_inscricao_depois == date(2026, 11, 12)
    assert dry[0].fim_inscricao_depois == date(2026, 11, 26)

    applied = run_backfill(db_session, apply=True)
    assert len(applied) == 1
    db_session.refresh(legado)
    assert legado.inicio_inscricao == date(2026, 11, 12)
    assert legado.fim_inscricao == date(2026, 11, 26)

    # Idempotente na segunda execução
    assert run_backfill(db_session, apply=True) == []
