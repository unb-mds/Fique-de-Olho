"""Testes automatizados para o scraper Samsung OceanBrasil (Unidade UnB) e para a prontidão de execução periódica.

Cobre:
1. OceanBrasilScraper (OCEAN):
   - Filtragem estrita da unidade Brasília/UnB (PCTec-UnB), excluindo USP (São Paulo) e UEA (Manaus);
   - Varredura mensal completa (/schedule) + enriquecimento de cursos (/course/{id}) + PDFs S3;
   - Extração dos editais de Residência Tecnológica em Saúde Digital (residencia.oceanbrasil.com) exclusivos da UnB.
2. Execução Periódica Contínua (todos os 21 scrapers + pipeline + service):
   - Transição automática de ano/semestre civil (sem anos engessados em 2026/2025);
   - Expiração/renovação de caches singleton em memória (TTL e limpeza por ciclo);
   - Normalização de URLs canônicas no SIGAA (;jsessionid=... e âncoras únicas por processo);
   - UPSERT periódico idempotente no banco (fechamento automático por fim_inscricao, status ou resultado_final,
     parse de datas ISO YYYY-MM-DD e proteção contra colisão de url_pdf compartilhado);
   - Orquestração periódica multi-portal (run_periodic_pipeline e sync_all_portais).
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, TipoDocumento
from app.modules.editais.models import Coleta
from app.modules.scraper import (
    OceanBrasilScraper,
    SCRAPERS_REGISTRY,
    get_scraper,
    ocean_scraper,
    run_periodic_pipeline,
)
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.dac import build_dac_url, dac_scraper
from app.modules.scraper.daces import build_daces_url, daces_scraper
from app.modules.scraper.dpi import build_dpi_url, dpi_scraper
from app.modules.scraper.ocean import (
    build_monthly_schedule_dates,
    build_ocean_activity_url,
    extract_ocean_residencia_unb_docs,
    format_ocean_activity_as_edital,
    is_unb_ocean_campus,
)
from app.modules.scraper.pipeline import parse_data_publicacao, upsert_edital
from app.modules.scraper.service import parse_date_pt, sync_all_portais, sync_portal_editais
from app.modules.scraper.sigaa import (
    canonicalize_sigaa_url,
    parse_sigaa_extensao_html,
    parse_sigaa_ppg_processos_html,
)


@pytest.fixture
def db_session():
    """Banco SQLite em memória isolado para validar ciclos periódicos do pipeline."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()


# ============================================================================
# 1. OceanBrasilScraper (Unidade UnB / Brasília)
# ============================================================================


def test_ocean_scraper_contract_and_registration():
    """Garante registro oficial do OceanBrasilScraper em SCRAPERS_REGISTRY."""
    assert isinstance(ocean_scraper, BaseScraper)
    assert issubclass(OceanBrasilScraper, BaseScraper)
    assert ocean_scraper.orgao_origem == "OCEAN"
    assert get_scraper("ocean") is ocean_scraper
    assert "OCEAN" in SCRAPERS_REGISTRY


def test_is_unb_ocean_campus_excludes_usp_and_uea():
    """Garante aceite exclusivo da unidade Brasília/UnB/PCTec e rejeição de São Paulo (USP) e Manaus (UEA)."""
    assert is_unb_ocean_campus("Brasília") is True
    assert is_unb_ocean_campus({"name": "Brasília", "address": "Parque Científico e Tecnológico da UnB - PCTec"}) is True
    assert is_unb_ocean_campus("Campus Darcy Ribeiro - UnB") is True

    assert is_unb_ocean_campus("São Paulo") is False
    assert is_unb_ocean_campus({"name": "São Paulo", "address": "Escola Politécnica da USP"}) is False
    assert is_unb_ocean_campus("Manaus") is False
    assert is_unb_ocean_campus({"name": "Manaus", "address": "EST - Universidade do Estado do Amazonas (UEA)"}) is False
    assert is_unb_ocean_campus("Campinas - UNICAMP") is False


def test_build_monthly_schedule_dates_periodic_windows():
    """Verifica geração das datas mensais com cobertura automática de virada de ano."""
    # Ano específico -> exatamente 12 meses
    dates_2027 = build_monthly_schedule_dates(year=2027)
    assert len(dates_2027) == 12
    assert dates_2027[0] == "2027-01-01"
    assert dates_2027[-1] == "2027-12-01"

    # Novembro -> inclui 12 meses do ano atual + Jan/Fev do ano seguinte
    nov_now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    dates_nov = build_monthly_schedule_dates(year=None, reference_now=nov_now)
    assert "2026-01-01" in dates_nov
    assert "2026-11-01" in dates_nov
    assert "2027-01-01" in dates_nov
    assert "2027-02-01" in dates_nov

    # Janeiro -> inclui Dezembro do ano anterior + 12 meses do ano atual
    jan_now = datetime(2028, 1, 5, tzinfo=timezone.utc)
    dates_jan = build_monthly_schedule_dates(year=None, reference_now=jan_now)
    assert dates_jan[0] == "2027-12-01"
    assert "2028-01-01" in dates_jan
    assert "2028-12-01" in dates_jan


def test_format_ocean_activity_as_edital_and_campus_guard():
    """Garante formatação completa da atividade mensal da UnB e descarte automático se for USP/UEA."""
    ref_now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    sessions = [
        {
            "eventGroupId": 6352,
            "eventGroupTitle": "Laboratório de Inteligência Artificial Aplicada à Saúde Digital",
            "trackTitle": "Inteligência Artificial",
            "modality": "Presencial",
            "campusName": "Brasília",
            "startDate": "2026-11-18T19:00:00.000Z",
            "endDate": "2026-11-20T22:00:00.000Z",
        }
    ]
    detail = {
        "id": 6352,
        "title": "Laboratório de Inteligência Artificial Aplicada à Saúde Digital",
        "trackName": "Inteligência Artificial",
        "modality": "Presencial",
        "enrollmentStatus": "open",
        "enrollmentStart": "2026-11-01T12:00:00.000Z",
        "certificateWorkload": 360,
        "description": "<p>Oficina prática presencial no laboratório Samsung Ocean UnB (PCTec).</p>",
        "targetAudience": "<p>Estudantes de graduação e pós-graduação da UnB e comunidade.</p>",
        "speakers": [{"name": "Profa. Dra. Maria Silva"}],
        "campus": {"name": "Brasília", "address": "PCTec - Campus Universitário Darcy Ribeiro, UnB"},
        "preparationMaterial": {
            "fileUrl": "https://oceanbrasil-files.s3.amazonaws.com/apostila_ia_unb.pdf"
        },
    }

    edital = format_ocean_activity_as_edital(
        group_id=6352,
        schedule_sessions=sessions,
        course_detail=detail,
        reference_now=ref_now,
    )
    assert edital is not None
    assert "Ocean UnB" in edital["titulo"]
    assert edital["unidade"] == "Ocean UnB (PCTec/UnB)"
    assert edital["campus"] == "Darcy Ribeiro"
    assert edital["status"] == "aberto"
    assert edital["ano"] == 2026
    assert edital["inicio_inscricao"] == "2026-11-01"
    assert edital["fim_inscricao"] == "2026-11-20"
    assert "Carga horária certificada: 6h" in edital["descricao"]
    assert "Profa. Dra. Maria Silva" in edital["descricao"]
    assert edital["link"] == build_ocean_activity_url(6352, detail["title"])
    assert len(edital["documentos"]) == 1
    assert edital["documentos"][0]["link"].endswith("apostila_ia_unb.pdf")

    # Atividade da USP (São Paulo) deve retornar None
    usp_detail = {**detail, "campus": {"name": "São Paulo", "address": "Poli-USP"}}
    usp_sessions = [{**sessions[0], "campusName": "São Paulo"}]
    assert format_ocean_activity_as_edital(6352, usp_sessions, course_detail=usp_detail, reference_now=ref_now) is None


def test_extract_ocean_residencia_unb_docs_filters_out_usp():
    """Garante extração exclusiva dos PDFs de Residência Ocean referentes à UnB/DF."""
    residencia_html = """
    <html>
      <body>
        <div class="card">
          <h3>Residência em Saúde Digital — Brasília (UnB / HUB-UnB)</h3>
          <a href="docs/edital_unb_2026_02.pdf">Edital de Abertura UnB Nº 02/2026</a>
          <a href="docs/unb2026-02resultadofinal.pdf">Resultado Final UnB 02/2026</a>
        </div>
        <div class="card">
          <h3>Residência Tecnológica — São Paulo (USP)</h3>
          <a href="docs/edital_usp_2026_01.pdf">Edital de Abertura USP Nº 01/2026</a>
        </div>
      </body>
    </html>
    """
    docs = extract_ocean_residencia_unb_docs(residencia_html, "https://residencia.oceanbrasil.com/")
    links = [d["link"] for d in docs]
    assert "https://residencia.oceanbrasil.com/docs/edital_unb_2026_02.pdf" in links
    assert "https://residencia.oceanbrasil.com/docs/unb2026-02resultadofinal.pdf" in links
    assert not any("usp" in lk.lower() for lk in links)
    res_doc = next(d for d in docs if "resultadofinal" in d["link"])
    assert res_doc["tipo"] == "resultado_final"


@patch("app.modules.scraper.ocean.httpx.Client")
def test_ocean_scraper_fetch_editais_and_docs_mock(mock_client_cls):
    """Testa fluxo completo do OceanBrasilScraper (agenda mensal Brasília + filtro USP/UEA + Residência UnB)."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    def fake_get(url, params=None, **kwargs):
        resp = MagicMock()
        resp.url = url
        resp.status_code = 200
        params = params or {}

        if url.endswith("/home/events"):
            resp.json.return_value = {
                "nextEventGroups": [
                    {
                        "id": 7001,
                        "eventGroupTitle": "Python para Ciência de Dados",
                        "trackTitle": "Ciência de Dados",
                        "campusName": "Brasília",
                        "modality": "Online",
                        "enrollmentStatus": "open",
                        "enrollmentStart": "2026-11-01T12:00:00.000Z",
                        "events": [{"startDate": "2026-11-25T22:00:00.000Z", "workload": 180}],
                    },
                    {
                        "id": 9999,
                        "eventGroupTitle": "Oficina Exclusiva Manaus UEA",
                        "trackTitle": "Android",
                        "campusName": "Manaus",
                        "modality": "Presencial",
                        "enrollmentStatus": "open",
                        "events": [{"startDate": "2026-11-25T22:00:00.000Z", "workload": 180}],
                    },
                ]
            }
            return resp

        if url.endswith("/schedule"):
            assert params.get("campus") == "Brasília"
            assert params.get("timeRange") == "MONTHLY"
            if params.get("date") == "2026-11-01":
                resp.json.return_value = [
                    {
                        "eventGroupId": 7001,
                        "eventGroupTitle": "Python para Ciência de Dados",
                        "trackTitle": "Ciência de Dados",
                        "campusName": "Brasília",
                        "modality": "Online",
                        "startDate": "2026-11-25T22:00:00.000Z",
                        "endDate": "2026-11-25T23:59:00.000Z",
                    }
                ]
            elif params.get("date") == "2026-03-01":
                resp.json.return_value = [
                    {
                        "eventGroupId": 6100,
                        "eventGroupTitle": "Introdução a IoT no PCTec UnB",
                        "trackTitle": "IoT",
                        "campusName": "Brasília",
                        "modality": "Presencial",
                        "startDate": "2026-03-10T19:00:00.000Z",
                        "endDate": "2026-03-10T22:00:00.000Z",
                    }
                ]
            else:
                resp.json.return_value = []
            return resp

        if url.endswith("/course/7001"):
            resp.json.return_value = {
                "id": 7001,
                "title": "Python para Ciência de Dados",
                "trackName": "Ciência de Dados",
                "modality": "Online",
                "enrollmentStatus": "open",
                "enrollmentStart": "2026-11-01T12:00:00.000Z",
                "certificateWorkload": 180,
                "campus": {"name": "Brasília"},
                "preparationMaterial": {"fileUrl": "https://cdn.oceanbrasil.com/slides_python.pdf"},
            }
            return resp

        if "residencia.oceanbrasil.com" in url:
            resp.text = '<a href="docs/edital_unb_2026_02.pdf">Edital UnB 02/2026</a>'
            return resp

        resp.status_code = 404
        resp.json.return_value = {}
        resp.text = ""
        return resp

    mock_client.get.side_effect = fake_get

    scraper = OceanBrasilScraper()
    editais = scraper.fetch_editais(year=2026)
    titles = [e["titulo"] for e in editais]

    assert any("Python para Ciência de Dados" in t for t in titles)
    assert any("Introdução a IoT no PCTec UnB" in t for t in titles)
    assert any("Residência Tecnológica em Saúde Digital" in t for t in titles)
    assert not any("Manaus" in t or "UEA" in t for t in titles)

    py_item = next(e for e in editais if "Python para Ciência de Dados" in e["titulo"])
    docs = scraper.fetch_documentos(py_item["link"])
    assert len(docs) == 1
    assert docs[0]["link"] == "https://cdn.oceanbrasil.com/slides_python.pdf"


# ============================================================================
# 2. Prontidão para Execução Periódica Contínua (Scrapers + Pipeline + Service)
# ============================================================================


def test_dynamic_year_and_semester_rollover_helpers():
    """Garante que DAC, DPI e DACES constroem URLs dinamicamente e fazem fallback na virada de ano/semestre."""
    assert build_dac_url(2028, 1) == "https://dds.dac.unb.br/2028-1/"
    assert build_dac_url(2028, 2) == "https://dds.dac.unb.br/2028-2/"
    assert build_dpi_url(2029) == "https://dpi.unb.br/editais/editais2029"
    assert build_daces_url(2029) == "https://acessibilidade.unb.br/editais-2029/"

    sample_html = '<a href="edital-auxilio-moradia.pdf">Edital Auxílio Moradia e Pesquisa PTA 2028</a>'

    # DAC em janeiro de 2028: se 2028-1 e 2028-2 ainda não existirem (404), faz fallback para 2027-2
    visited_dac: list[str] = []

    def fake_dac_get(url, **kwargs):
        visited_dac.append(url)
        resp = MagicMock()
        resp.url = url
        if url.endswith("/2027-2/"):
            resp.status_code = 200
            resp.text = sample_html
            return resp
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))

    with patch("app.modules.scraper.dac.datetime") as mock_dt, patch(
        "app.modules.scraper.dac.httpx.get", side_effect=fake_dac_get
    ):
        mock_dt.now.return_value = datetime(2028, 1, 10, tzinfo=timezone.utc)
        dac_items = dac_scraper.fetch_editais()
    assert len(dac_items) == 1
    assert visited_dac[:3] == [
        "https://dds.dac.unb.br/2028-1/",
        "https://dds.dac.unb.br/2028-2/",
        "https://dds.dac.unb.br/2027-2/",
    ]

    # DPI em janeiro de 2029: tenta editais2029 e faz fallback para editais2028
    visited_dpi: list[str] = []

    def fake_dpi_get(url, **kwargs):
        visited_dpi.append(url)
        resp = MagicMock()
        resp.url = url
        if url.endswith("editais2028"):
            resp.status_code = 200
            resp.text = sample_html
            return resp
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))

    with patch("app.modules.scraper.dpi.datetime") as mock_dt, patch(
        "app.modules.scraper.dpi.httpx.get", side_effect=fake_dpi_get
    ):
        mock_dt.now.return_value = datetime(2029, 1, 5, tzinfo=timezone.utc)
        dpi_items = dpi_scraper.fetch_editais()
    assert len(dpi_items) == 1
    assert visited_dpi == [
        "https://dpi.unb.br/editais/editais2029",
        "https://dpi.unb.br/editais/editais2028",
    ]

    # DACES em janeiro de 2029: tenta editais-2029/ e faz fallback para editais-2028/
    visited_daces: list[str] = []

    def fake_daces_get(url, **kwargs):
        visited_daces.append(url)
        resp = MagicMock()
        resp.url = url
        if url.endswith("editais-2028/"):
            resp.status_code = 200
            resp.text = sample_html
            return resp
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))

    with patch("app.modules.scraper.daces.datetime") as mock_dt, patch(
        "app.modules.scraper.daces.httpx.get", side_effect=fake_daces_get
    ):
        mock_dt.now.return_value = datetime(2029, 1, 5, tzinfo=timezone.utc)
        daces_items = daces_scraper.fetch_editais()
    assert len(daces_items) == 1
    assert visited_daces == [
        "https://acessibilidade.unb.br/editais-2029/",
        "https://acessibilidade.unb.br/editais-2028/",
    ]


def test_sigaa_periodic_canonical_urls_and_non_colliding_anchors():
    """Garante remoção de ;jsessionid=... e âncoras únicas por processo no SIGAA."""
    dirty_url = "https://sigaa.unb.br/sigaa/public/processo_seletivo/detalhes.jsf;jsessionid=ABC987654.node2?id=445"
    assert canonicalize_sigaa_url(dirty_url) == "https://sigaa.unb.br/sigaa/public/processo_seletivo/detalhes.jsf?id=445"

    ppg_html = """
    <table>
      <tr><td>Período</td><td>Processos Seletivos</td></tr>
      <tr>
        <td>01/10/2026 a 30/11/2026</td>
        <td><a href="#" onclick="jsfcljs(form,{'id':'1001'},'_blank')"><span class="destaqueProcessoeletivo">Mestrado 2027/1</span></a></td>
      </tr>
      <tr>
        <td>01/10/2026 a 30/11/2026</td>
        <td><a href="#" onclick="jsfcljs(form,{'id':'1002'},'_blank')"><span class="destaqueProcessoeletivo">Doutorado 2027/1</span></a></td>
      </tr>
    </table>
    """
    ppg_items = parse_sigaa_ppg_processos_html(ppg_html, "Computação Aplicada", "999")
    assert len(ppg_items) == 2
    assert ppg_items[0]["link"] != ppg_items[1]["link"]
    assert ppg_items[0]["link"].endswith("#processo-1001")
    assert ppg_items[1]["link"].endswith("#processo-1002")

    ext_html = """
    <table class="listagem">
      <tr>
        <td>Oficina de Robótica Coordenação: PROF A</td><td>CURSO</td><td>TEC</td><td>FGA</td><td>FGA</td>
        <td>01/01/2024 a 10/01/2024</td><td>15/01/2024 a 20/01/2024</td><td>30</td>
      </tr>
      <tr>
        <td>Oficina de IA Coordenação: PROF B</td><td>CURSO</td><td>TEC</td><td>CIC</td><td>Darcy Ribeiro</td>
        <td>01/01/2099 a 31/12/2099</td><td>01/02/2099 a 28/02/2099</td><td>40</td>
      </tr>
    </table>
    """
    ext_items = parse_sigaa_extensao_html(ext_html)
    assert len(ext_items) == 2
    assert ext_items[0]["link"] != ext_items[1]["link"]
    assert ext_items[0]["status"] == "fechado"  # prazo expirado em 2024
    assert ext_items[1]["status"] == "aberto"   # prazo futuro


def test_parse_data_publicacao_and_parse_date_pt_support_iso_dates():
    """Garante que datas ISO (WordPress/Tainacan/Ocean/Cebraspe) são convertidas com precisão."""
    dt_iso = parse_data_publicacao("2026-09-22")
    assert (dt_iso.year, dt_iso.month, dt_iso.day) == (2026, 9, 22)

    dt_iso_ts = parse_data_publicacao("2027-04-05T14:30:00Z")
    assert (dt_iso_ts.year, dt_iso_ts.month, dt_iso_ts.day) == (2027, 4, 5)

    assert parse_date_pt("2026-09-22") == date(2026, 9, 22)


def test_periodic_upsert_edital_status_transitions_and_shared_pdf_safety(db_session):
    """Valida ciclo periódico: abertura -> fechamento automático por prazo/status + segurança de url_pdf compartilhado."""
    future_deadline = (datetime.now(timezone.utc).date() + timedelta(days=15)).isoformat()
    past_deadline = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    shared_pdf = "https://www.gov.br/hubrasil/pt-br/regulamento_compartilhado.pdf"

    # Ciclo 1: Edital inserido como aberto com documento embutido e prazo futuro
    edital_ciclo_1 = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "PIC HUB-UnB — Edição Periódica",
            "link": "https://www.gov.br/hubrasil/pt-br/pic-periodico",
            "url_pdf": shared_pdf,
            "data_publicacao": "2026-05-14",
            "inicio_inscricao": "2026-05-14",
            "fim_inscricao": future_deadline,
            "status": "aberto",
            "documentos": [
                {"titulo": "Edital de Abertura", "link": shared_pdf, "tipo": "original"}
            ],
        },
    )
    assert edital_ciclo_1.status == StatusEdital.ABERTO
    assert len(edital_ciclo_1.documentos) == 1

    # Segundo edital diferente que aponta para o MESMO PDF compartilhado não deve disparar IntegrityError
    edital_compartilhado = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "PIT HUB-UnB — Edição Periódica",
            "link": "https://www.gov.br/hubrasil/pt-br/pit-periodico",
            "url_pdf": shared_pdf,
            "data_publicacao": "2026-05-14",
            "status": "aberto",
        },
    )
    assert edital_compartilhado.id != edital_ciclo_1.id
    assert db_session.query(Edital).count() == 2

    # Ciclo 2 (execução periódica dias depois): prazo expirou -> deve fechar automaticamente sem duplicar
    edital_ciclo_2 = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "PIC HUB-UnB — Edição Periódica",
            "link": "https://www.gov.br/hubrasil/pt-br/pic-periodico",
            "url_pdf": shared_pdf,
            "data_publicacao": "2026-05-14",
            "inicio_inscricao": "2026-05-14",
            "fim_inscricao": past_deadline,
            "status": "aberto",
            "documentos": [
                {"titulo": "Edital de Abertura", "link": shared_pdf, "tipo": "original"}
            ],
        },
    )
    assert edital_ciclo_2.id == edital_ciclo_1.id
    assert edital_ciclo_2.status == StatusEdital.ENCERRADO
    assert db_session.query(Edital).count() == 2


def test_periodic_multi_portal_sync_and_error_isolation(db_session, monkeypatch):
    """Garante que sync_all_portais e run_periodic_pipeline sincronizam múltiplos órgãos e isolam falhas."""
    fake_hub = MagicMock()
    fake_hub.fetch_editais.return_value = [
        {
            "titulo": "Concurso de Inovação em Saúde Digital — HUB-UnB",
            "link": "https://www.gov.br/hubrasil/pt-br/pesquisa/editais/concurso-de-inovacao",
            "data_publicacao": "10/06/2026",
            "status": "aberto",
            "campus": "Darcy Ribeiro",
            "tipo": "Pesquisa, Inovação e Saúde Digital",
            "documentos": [
                {"titulo": "Edital Saúde Digital", "link": "https://www.gov.br/hubrasil/edital_sd.pdf", "tipo": "original"}
            ],
        }
    ]

    fake_ocean = MagicMock()
    fake_ocean.fetch_editais.return_value = [
        {
            "titulo": "Curso de IA Generativa — Ocean UnB",
            "link": "https://www.oceanbrasil.com/atividades/8001-curso-de-ia-generativa",
            "data_publicacao": "05/11/2026",
            "status": "aberto",
            "campus": "Darcy Ribeiro",
            "tipo": "Extensão",
            "documentos": [],
        }
    ]

    failing_portal = MagicMock()
    failing_portal.fetch_editais.side_effect = RuntimeError("Portal temporariamente em manutenção")

    monkeypatch.setitem(SCRAPERS_REGISTRY, "HUB", fake_hub)
    monkeypatch.setitem(SCRAPERS_REGISTRY, "OCEAN", fake_ocean)
    monkeypatch.setitem(SCRAPERS_REGISTRY, "FAL", failing_portal)

    resumo_ciclo_1 = sync_all_portais(
        db=db_session,
        orgaos=["HUB", "OCEAN", "FAL"],
        max_items_per_orgao=10,
    )
    assert resumo_ciclo_1["status"] == "success"
    assert resumo_ciclo_1["novos_editais"] == 2
    assert resumo_ciclo_1["portais"]["HUB"]["status"] == "success"
    assert resumo_ciclo_1["portais"]["OCEAN"]["status"] == "success"
    assert resumo_ciclo_1["portais"]["FAL"]["status"] == "error"

    # Ciclo 2 idêntico: 0 novos editais e 0 atualizados (idempotência periódica perfeita)
    resumo_ciclo_2 = sync_all_portais(
        db=db_session,
        orgaos=["HUB", "OCEAN"],
        max_items_per_orgao=10,
    )
    assert resumo_ciclo_2["novos_editais"] == 0
    assert resumo_ciclo_2["editais_atualizados"] == 0

    # Ciclo 3: HUB publica Resultado Final -> atualiza o edital existente e fecha seu status
    fake_hub.fetch_editais.return_value[0]["documentos"].append(
        {"titulo": "Resultado Final", "link": "https://www.gov.br/hubrasil/res_final_sd.pdf", "tipo": "resultado_final"}
    )
    resumo_ciclo_3 = sync_portal_editais(db=db_session, orgao="HUB", max_items=10)
    assert resumo_ciclo_3["novos_editais"] == 0
    assert resumo_ciclo_3["editais_atualizados"] == 1

    hub_db = db_session.query(Edital).filter_by(
        url_pagina="https://www.gov.br/hubrasil/pt-br/pesquisa/editais/concurso-de-inovacao"
    ).one()
    assert hub_db.status == StatusEdital.ENCERRADO
    assert len(hub_db.documentos) == 2

    # Verifica registros de auditoria na tabela Coleta
    coletas = db_session.query(Coleta).all()
    assert len(coletas) == 6  # 3 no ciclo 1 + 2 no ciclo 2 + 1 no ciclo 3

    # Valida também run_periodic_pipeline
    por_orgao = run_periodic_pipeline(db=db_session, orgaos=["HUB", "OCEAN", "FAL"], fetch_docs=False)
    assert len(por_orgao["HUB"]) == 1
    assert len(por_orgao["OCEAN"]) == 1
    assert por_orgao["FAL"] == []


@pytest.mark.live
def test_ocean_brasil_unb_live_monthly_activities():
    """Teste ao vivo na API de produção do OceanBrasil validando atividades mensais da UnB e Residência."""
    scraper = OceanBrasilScraper(timeout=10.0)
    editais = scraper.fetch_editais(year=2026)
    assert isinstance(editais, list)
    if editais:
        for item in editais[:15]:
            assert item["titulo"]
            assert "UnB" in item["unidade"]
            assert item["campus"] == "Darcy Ribeiro"
            assert "USP" not in item["unidade"]
            assert "UEA" not in item["unidade"]
