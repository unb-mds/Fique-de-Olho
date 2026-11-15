from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, TipoDocumento
from app.modules.editais.service import serialize_edital
from app.modules.scraper.pdf import (
    PDFCorruptedError,
    PDFDocumentExtraction,
    PDFDownloadError,
    PDFPageExtraction,
)
from app.modules.scraper.pipeline import (
    _coerce_valor_bolsa,
    _coerce_vagas,
    _enrich_edital_metadata,
    parse_data_publicacao,
    run_periodic_pipeline,
    run_pipeline,
    upsert_edital,
)


@pytest.fixture
def db_session(monkeypatch):
    """Cria banco SQLite em memória isolado (com enforcement de CHECK constraints) e mock de extract_pdf por padrão."""
    import app.modules.scraper.pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod,
        "extract_pdf",
        lambda url, **kw: PDFDocumentExtraction(
            source=str(url), num_pages=1, full_text="", pages=[], tables=[]
        ),
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA ignore_check_constraints = OFF")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_parse_data_publicacao():
    dt1 = parse_data_publicacao("23 de setembro de 2026")
    assert dt1.year == 2026
    assert dt1.month == 9
    assert dt1.day == 23

    dt2 = parse_data_publicacao("15/03/2025")
    assert dt2.year == 2025
    assert dt2.month == 3
    assert dt2.day == 15

    dt3 = parse_data_publicacao("")
    assert dt3.year == datetime.now(timezone.utc).year


def test_upsert_edital_insert_new(db_session):
    edital_data = {
        "titulo": "Edital Monitoria DEG 01/2026",
        "link": "https://deg.unb.br/editais/monitoria-2026",
        "data_publicacao": "23 de setembro de 2026",
    }
    docs_data = [
        {
            "titulo": "Edital Completo",
            "link": "https://deg.unb.br/docs/edital-01.pdf",
            "tipo": "original",
        }
    ]

    edital = upsert_edital(db=db_session, edital_data=edital_data, documentos_data=docs_data)

    assert edital.id is not None
    assert edital.titulo == "Edital Monitoria DEG 01/2026"
    assert edital.status == StatusEdital.ABERTO
    assert len(edital.documentos) == 1
    assert edital.documentos[0].tipo_documento == TipoDocumento.ORIGINAL


def test_upsert_edital_update_and_idempotence(db_session):
    edital_data = {
        "titulo": "Edital Monitoria DEG 01/2026",
        "link": "https://deg.unb.br/editais/monitoria-2026",
        "data_publicacao": "23 de setembro de 2026",
    }
    docs_data_1 = [
        {
            "titulo": "Edital Completo",
            "link": "https://deg.unb.br/docs/edital-01.pdf",
            "tipo": "original",
        }
    ]

    # Primeira execução: insere
    upsert_edital(db=db_session, edital_data=edital_data, documentos_data=docs_data_1)
    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 1

    # Segunda execução idêntica: não duplica
    upsert_edital(db=db_session, edital_data=edital_data, documentos_data=docs_data_1)
    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 1

    # Terceira execução com novo documento (resultado_final): adiciona doc e muda status para ENCERRADO
    docs_data_2 = docs_data_1 + [
        {
            "titulo": "Resultado Final Monitoria",
            "link": "https://deg.unb.br/docs/resultado_final.pdf",
            "tipo": "resultado_final",
        }
    ]
    edital_atualizado = upsert_edital(
        db=db_session,
        edital_data=edital_data,
        documentos_data=docs_data_2,
    )

    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 2
    assert edital_atualizado.status == StatusEdital.ENCERRADO


def test_run_pipeline_persists_scraped_data(db_session, monkeypatch):
    from app.modules.scraper import deg

    fake_editais = [
        {
            "titulo": "Edital DEG 01/2026",
            "link": "https://deg.unb.br/editais/01-2026",
            "data_publicacao": "10 de fevereiro de 2026",
        },
        {
            "titulo": "Edital DEG 02/2026",
            "link": "https://deg.unb.br/editais/02-2026",
            "data_publicacao": "15 de março de 2026",
        },
    ]

    def fake_fetch_editais(year=None):
        return fake_editais

    def fake_fetch_documentos(url):
        if "01-2026" in url:
            return [
                {"titulo": "Edital", "link": f"{url}/doc.pdf", "tipo": "original"},
                {"titulo": "Resultado", "link": f"{url}/resultado.pdf", "tipo": "resultado_final"},
            ]
        return [{"titulo": "Edital", "link": f"{url}/doc.pdf", "tipo": "original"}]

    monkeypatch.setattr(deg, "fetch_editais", fake_fetch_editais)
    monkeypatch.setattr(deg, "fetch_documentos", fake_fetch_documentos)

    salvos = run_pipeline(db=db_session, year=2026)

    assert len(salvos) == 2
    assert db_session.query(Edital).count() == 2

    e1 = db_session.query(Edital).filter_by(url_pagina="https://deg.unb.br/editais/01-2026").first()
    assert e1.status == StatusEdital.ENCERRADO
    assert e1.orgao_emissor == "DEG"
    assert len(e1.documentos) == 2

    e2 = db_session.query(Edital).filter_by(url_pagina="https://deg.unb.br/editais/02-2026").first()
    assert e2.status == StatusEdital.ABERTO
    assert e2.orgao_emissor == "DEG"
    assert len(e2.documentos) == 1


# ============================================================================
# Testes TDD da Issue #53 — Enriquecimento de Metadados + PDF + Status
# ============================================================================


def test_1_metadados_nativos_estruturados_sem_chamar_extract_pdf(db_session, monkeypatch):
    """1. Metadados nativos estruturados completos + texto_extraido -> persiste tudo sem chamar extract_pdf."""
    import app.modules.scraper.pipeline as pipeline_mod

    called = {"count": 0}

    def fail_if_called(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("extract_pdf não deveria ser chamado quando todos os metadados já estão presentes")

    monkeypatch.setattr(pipeline_mod, "extract_pdf", fail_if_called)

    today = datetime.now(timezone.utc).date()
    ini_futuro = (today + timedelta(days=2)).isoformat()
    fim_futuro = (today + timedelta(days=20)).isoformat()

    edital = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital PIBIC 2026/2027",
            "link": "https://proic.unb.br/editais/pibic-2026",
            "url_pdf": "https://proic.unb.br/editais/pibic-2026.pdf",
            "orgao_emissor": "PROIC",
            "assunto": "Iniciação Científica e Tecnológica",
            "campus": "Darcy Ribeiro",
            "vagas": "15 vagas",
            "valor_bolsa": "R$ 700,00",
            "inicio_inscricao": ini_futuro,
            "fim_inscricao": fim_futuro,
            "texto_extraido": "Texto já extraído previamente pelo scraper estruturado.",
        },
    )

    assert called["count"] == 0
    assert edital.orgao_emissor == "PROIC"
    assert edital.assunto == "Iniciação Científica e Tecnológica"
    assert edital.campus == "Darcy Ribeiro"
    assert edital.vagas == 15
    assert edital.valor_bolsa == Decimal("700.00")
    assert edital.inicio_inscricao == today + timedelta(days=2)
    assert edital.fim_inscricao == today + timedelta(days=20)
    assert edital.status == StatusEdital.ABERTO
    assert edital.status_processamento == "processado"

    # Verifica também coercões diversas de vagas e valor_bolsa
    assert _coerce_vagas("2100") == 2100
    assert _coerce_vagas("1 vaga") == 1
    assert _coerce_vagas("2 + CR") == 2
    assert _coerce_vagas("não informado") is None
    assert _coerce_valor_bolsa("R$ 1.500,00") == Decimal("1500.00")
    assert _coerce_valor_bolsa(700.0) == Decimal("700.00")

    # E exposição em serialize_edital
    serial = serialize_edital(edital, detail=True)
    assert serial["orgao_emissor"] == "PROIC"
    assert serial["assunto"] == "Iniciação Científica e Tecnológica"
    assert serial["vagas"] == 15
    assert serial["valor_bolsa"] == 700.0
    assert serial["valor"] == "R$ 700,00"


def test_2_fallback_via_pdf_preenche_metadados_e_recalcula_status(db_session, monkeypatch):
    """2. Fallback via PDF extrai prazos, vagas, bolsa, texto_extraido e recalcula status automaticamente."""
    import app.modules.scraper.pipeline as pipeline_mod

    today = datetime.now(timezone.utc).date()
    past_ini = (today - timedelta(days=30)).strftime("%d/%m/%Y")
    past_fim = (today - timedelta(days=5)).strftime("%d/%m/%Y")
    future_ini = (today + timedelta(days=1)).strftime("%d/%m/%Y")
    future_fim = (today + timedelta(days=15)).strftime("%d/%m/%Y")

    def fake_extract_pdf(url, timeout=10.0):
        if "vencido.pdf" in url:
            txt = (
                "UNIVERSIDADE DE BRASÍLIA - DECANATO DE EXTENSÃO (DEX)\n"
                "Campus FGA (Gama). Total de 12 vagas com bolsa de R$ 850,00.\n"
                f"Inscrições: {past_ini} a {past_fim}."
            )
        else:
            txt = (
                "UNIVERSIDADE DE BRASÍLIA - DECANATO DE PÓS-GRADUAÇÃO (DPG)\n"
                "Faculdade de Ceilândia - FCE. 6 vagas. Bolsa de R$ 1.500,00.\n"
                f"Inscrições: {future_ini} a {future_fim}."
            )
        return PDFDocumentExtraction(
            source=url,
            num_pages=1,
            full_text=txt,
            pages=[PDFPageExtraction(index=1, text=txt)],
            tables=[],
        )

    monkeypatch.setattr(pipeline_mod, "extract_pdf", fake_extract_pdf)

    # Caso A: fim_inscricao extraído do PDF já passou -> status deve ser ENCERRADO
    ed_vencido = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital Extensão DEX",
            "link": "https://dex.unb.br/editais/ext-01",
            "url_pdf": "https://dex.unb.br/editais/vencido.pdf",
        },
    )
    assert ed_vencido.orgao_emissor == "DEX"
    assert ed_vencido.campus == "FGA"
    assert ed_vencido.vagas == 12
    assert ed_vencido.valor_bolsa == Decimal("850.00")
    assert ed_vencido.inicio_inscricao == today - timedelta(days=30)
    assert ed_vencido.fim_inscricao == today - timedelta(days=5)
    assert "DECANATO DE EXTENSÃO" in (ed_vencido.texto_extraido or "")
    assert ed_vencido.status_processamento == "processado"
    assert ed_vencido.status == StatusEdital.ENCERRADO

    # Caso B: fim_inscricao extraído do PDF é futuro -> status deve ser ABERTO
    ed_aberto = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital Pós-Graduação DPG",
            "link": "https://dpg.unb.br/editais/pos-02",
            "documentos": [
                {"titulo": "Edital de Abertura", "link": "https://dpg.unb.br/editais/futuro.pdf", "tipo": "original"}
            ],
        },
    )
    assert ed_aberto.orgao_emissor == "DPG"
    assert ed_aberto.campus == "FCE"
    assert ed_aberto.vagas == 6
    assert ed_aberto.valor_bolsa == Decimal("1500.00")
    assert ed_aberto.fim_inscricao == today + timedelta(days=15)
    assert ed_aberto.status_processamento == "processado"
    assert ed_aberto.status == StatusEdital.ABERTO


def test_3_prioridade_estruturado_sobre_pdf(db_session, monkeypatch):
    """3. Campos estruturados fornecidos pelo scraper nunca são sobrescritos pelos valores do PDF."""
    import app.modules.scraper.pipeline as pipeline_mod

    def fake_extract_pdf(url, timeout=10.0):
        txt = (
            "UNIVERSIDADE DE BRASÍLIA - DEG\n"
            "Faculdade de Planaltina (FUP). Total de 99 vagas com bolsa de R$ 1.200,00.\n"
            "Inscrições: 01/01/2026 a 31/12/2026."
        )
        return PDFDocumentExtraction(
            source=url,
            num_pages=1,
            full_text=txt,
            pages=[PDFPageExtraction(index=1, text=txt)],
            tables=[],
        )

    monkeypatch.setattr(pipeline_mod, "extract_pdf", fake_extract_pdf)

    edital = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital HUB Pesquisa Clínica",
            "link": "https://www.gov.br/hubrasil/edital-01",
            "url_pdf": "https://www.gov.br/hubrasil/edital-01.pdf",
            "orgao_emissor": "HUB",
            "campus": "Darcy Ribeiro",
            "vagas": 4,
            "inicio_inscricao": "2026-05-10",
            # valor_bolsa e fim_inscricao ausentes no scraper -> devem vir do PDF
        },
    )

    # Preservados do scraper:
    assert edital.orgao_emissor == "HUB"
    assert edital.campus == "Darcy Ribeiro"
    assert edital.vagas == 4
    assert edital.inicio_inscricao == date(2026, 5, 10)
    # Preenchidos pelo fallback do PDF:
    assert edital.valor_bolsa == Decimal("1200.00")
    assert edital.fim_inscricao == date(2026, 12, 31)
    assert edital.texto_extraido is not None


def test_4_status_encerrado_por_resultado_final_e_homologacao(db_session):
    """4. Edital com documento resultado_final (ou homologação) fica ENCERRADO mesmo com fim_inscricao futuro."""
    future_fim = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    edital = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital Seleção Simplificada",
            "link": "https://deg.unb.br/editais/selecao-99",
            "fim_inscricao": future_fim,
            "documentos": [
                {"titulo": "Edital Abertura", "link": "https://deg.unb.br/abertura.pdf", "tipo": "original"},
                {"titulo": "Homologação do Resultado Final", "link": "https://deg.unb.br/homolog.pdf", "tipo": "homologacao"},
            ],
        },
    )
    assert edital.status == StatusEdital.ENCERRADO
    tipos = {d.tipo_documento for d in edital.documentos}
    assert TipoDocumento.RESULTADO_FINAL in tipos

    # E em um update subsequente sem passar documentos novos mas mantendo os existentes no banco:
    edital_reup = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital Seleção Simplificada Atualizado",
            "link": "https://deg.unb.br/editais/selecao-99",
            "fim_inscricao": future_fim,
        },
    )
    assert edital_reup.status == StatusEdital.ENCERRADO


def test_5_isolamento_de_falhas_no_pdf_mantem_persistencia(db_session, monkeypatch, caplog):
    """5. Falhas em extract_pdf (PDFCorruptedError / PDFDownloadError) registram warning e salvam com status_processamento='erro'."""
    import app.modules.scraper.pipeline as pipeline_mod

    def raise_corrupted(url, timeout=10.0):
        if "timeout" in url:
            raise PDFDownloadError("Timeout ao baixar PDF")
        raise PDFCorruptedError("PDF corrompido ou ilegível")

    monkeypatch.setattr(pipeline_mod, "extract_pdf", raise_corrupted)

    with caplog.at_level("WARNING"):
        ed1 = upsert_edital(
            db=db_session,
            edital_data={
                "titulo": "Edital com PDF Corrompido",
                "link": "https://deg.unb.br/editais/corrompido",
                "url_pdf": "https://deg.unb.br/editais/corrompido.pdf",
                "orgao_emissor": "DEG",
            },
        )
        ed2 = upsert_edital(
            db=db_session,
            edital_data={
                "titulo": "Edital com PDF Timeout",
                "link": "https://deg.unb.br/editais/timeout",
                "url_pdf": "https://deg.unb.br/editais/timeout.pdf",
                "orgao_emissor": "DEG",
            },
        )

    assert ed1.id is not None
    assert ed1.status_processamento == "erro"
    assert ed2.id is not None
    assert ed2.status_processamento == "erro"
    assert db_session.query(Edital).count() == 2
    assert any("Falha ao extrair/enriquecer PDF" in rec.message for rec in caplog.records)


def test_6_sanitizacao_de_constraint_periodo_inscricao(db_session, monkeypatch):
    """6. inicio_inscricao > fim_inscricao (no scraper ou no PDF) é sanitizado e não viola editais_periodo_inscricao_ck."""
    import app.modules.scraper.pipeline as pipeline_mod

    # Caso 1: Datas invertidas vindas do scraper
    ed1 = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital Datas Invertidas Scraper",
            "link": "https://deg.unb.br/editais/invertido-1",
            "inicio_inscricao": "2026-10-25",
            "fim_inscricao": "2026-10-10",
        },
        enable_pdf_enrichment=False,
    )
    assert ed1.id is not None
    assert ed1.inicio_inscricao is None
    assert ed1.fim_inscricao == date(2026, 10, 10)

    # Caso 2: PDF retorna fim_inscricao anterior ao inicio_inscricao do scraper
    def fake_pdf_inconsistente(url, timeout=10.0):
        txt = "Inscrições: 01/05/2026 a 05/05/2026."
        return PDFDocumentExtraction(source=url, num_pages=1, full_text=txt)

    monkeypatch.setattr(pipeline_mod, "extract_pdf", fake_pdf_inconsistente)

    ed2 = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital Conflito Scraper x PDF",
            "link": "https://deg.unb.br/editais/invertido-2",
            "url_pdf": "https://deg.unb.br/editais/invertido-2.pdf",
            "inicio_inscricao": "2026-06-01",
        },
    )
    assert ed2.id is not None
    assert ed2.inicio_inscricao == date(2026, 6, 1)
    assert ed2.fim_inscricao is None


def test_7_idempotencia_skip_de_reprocessamento_pdf(db_session, monkeypatch):
    """7. Segunda execução com mesmo hash_conteudo, url_pdf inalterado e texto_extraido já preenchido não baixa o PDF novamente."""
    import app.modules.scraper.pipeline as pipeline_mod

    calls = {"count": 0}

    def counting_extract_pdf(url, timeout=10.0):
        calls["count"] += 1
        txt = "UNIVERSIDADE DE BRASÍLIA - DEG. 5 vagas. Inscrições: 10/10/2026 a 20/10/2026."
        return PDFDocumentExtraction(source=url, num_pages=1, full_text=txt)

    monkeypatch.setattr(pipeline_mod, "extract_pdf", counting_extract_pdf)

    payload = {
        "titulo": "Edital Idempotente PDF",
        "link": "https://deg.unb.br/editais/idempotente",
        "url_pdf": "https://deg.unb.br/editais/idempotente.pdf",
        "data_publicacao": "2026-10-01",
    }

    # 1ª execução: faz download e extrai texto_extraido (calls == 1)
    e1 = upsert_edital(db=db_session, edital_data=payload)
    assert calls["count"] == 1
    assert e1.texto_extraido is not None
    assert e1.vagas == 5

    # 2ª execução idêntica: mesmo hash_conteudo, mesmo url_pdf e texto_extraido já no banco -> NÃO chama extract_pdf
    e2 = upsert_edital(db=db_session, edital_data=payload)
    assert calls["count"] == 1
    assert e2.id == e1.id
    assert e2.texto_extraido == e1.texto_extraido
    assert e2.vagas == 5
    assert e2.status_processamento == "processado"


# ============================================================================
# Testes TDD da Issue #72 — Persistência de url_pdf vs url_pagina e Documentos
# ============================================================================


def test_issue_72_url_pdf_direta_e_url_pagina_preservada(db_session):
    """Valida que edital.url_pdf recebe a URL direta do PDF (.pdf) e edital.url_pagina preserva a página web."""
    pagina_web = "https://deg.unb.br/editais/monitoria-graduacao-2026"
    pdf_abertura = "https://deg.unb.br/arquivos/edital_abertura_01_2026.pdf"
    pdf_retificacao = "https://deg.unb.br/arquivos/retificacao_01_2026.pdf"
    pdf_resultado = "https://deg.unb.br/arquivos/resultado_provisorio_01_2026.pdf"

    edital = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital de Monitoria 01/2026",
            "link": pagina_web,
            "data_publicacao": "2026-09-10",
        },
        documentos_data=[
            {"titulo": "Edital de Abertura", "link": pdf_abertura, "tipo": "original"},
            {"titulo": "Retificação Nº 01", "link": pdf_retificacao, "tipo": "retificacao"},
            {"titulo": "Resultado Provisório", "link": pdf_resultado, "tipo": "resultado_provisorio"},
        ],
    )

    assert edital.url_pagina == pagina_web
    assert edital.url_pdf == pdf_abertura
    assert edital.url_pdf.endswith(".pdf")
    assert len(edital.documentos) == 3

    # Reexecução sem passar documentos não deve sobrescrever o url_pdf válido com None ou url_pagina
    edital_reexec = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Edital de Monitoria 01/2026",
            "link": pagina_web,
            "data_publicacao": "2026-09-10",
        },
        documentos_data=[],
    )
    assert edital_reexec.id == edital.id
    assert edital_reexec.url_pagina == pagina_web
    assert edital_reexec.url_pdf == pdf_abertura
    assert len(edital_reexec.documentos) == 3


def test_issue_72_sem_pdf_nao_grava_url_pagina_em_url_pdf(db_session):
    """Se não houver PDF nos anexos e a página for HTML, url_pdf permanece None (e atualiza quando PDF surge)."""
    pagina_web = "https://dex.unb.br/noticias/chamada-extensao-2026"
    edital = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Chamada de Extensão DEX 2026",
            "link": pagina_web,
            "data_publicacao": "2026-10-01",
        },
        documentos_data=[],
    )
    assert edital.url_pagina == pagina_web
    assert edital.url_pdf is None

    # Quando o documento PDF oficial é publicado posteriormente, url_pdf passa a armazenar o link .pdf
    pdf_oficial = "https://dex.unb.br/arquivos/chamada_extensao_2026.pdf"
    edital_atualizado = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "Chamada de Extensão DEX 2026",
            "link": pagina_web,
            "data_publicacao": "2026-10-01",
        },
        documentos_data=[{"titulo": "Edital PDF", "link": pdf_oficial, "tipo": "original"}],
    )
    assert edital_atualizado.id == edital.id
    assert edital_atualizado.url_pagina == pagina_web
    assert edital_atualizado.url_pdf == pdf_oficial
