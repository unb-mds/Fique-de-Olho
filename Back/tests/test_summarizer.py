"""Testes TDD das Issues #77 e #106 — Resumo automático e normalização de títulos vagos.

Cobre a abordagem híbrida:
- Camada 1 (heurística determinística local em ``parser.py``);
- Camada 2 (LLM Gemini com fallback transparente em ``summarizer.py``);
- Integração com ``upsert_edital`` no pipeline de persistência.
"""

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, Edital
from app.modules.scraper import summarizer
from app.modules.scraper.parser import (
    extrair_objeto_edital,
    is_vague_title,
    reconstruir_titulo_edital,
    truncar_texto,
)
from app.modules.scraper.pdf import PDFDocumentExtraction
from app.modules.scraper.summarizer import (
    enrich_title_and_summary,
    enrich_title_and_summary_async,
    is_generic_summary,
    summarize_edital,
)


TEXTO_EDITAL_TUTORES = """SEI/UnB - 11223344 - Edital
UNIVERSIDADE DE BRASÍLIA
CENTRO DE EDUCAÇÃO A DISTÂNCIA
EDITAL Nº 158/2024
1. DO OBJETO
1.1 O presente edital tem por objeto a seleção de tutores a distância
para atuarem nos cursos de graduação da Universidade Aberta do Brasil (UAB/UnB),
com bolsa da CAPES, destinada a estudantes de pós-graduação e professores da rede pública.
Página 1 de 7
Referência: Processo nº 23106.012345/2024-11 SEI nº 11223344
2. DAS INSCRIÇÕES
2.1 As inscrições serão realizadas de 10/10/2024 a 20/10/2024.
"""

TEXTO_EDITAL_PIBIC = """UNIVERSIDADE DE BRASÍLIA
DECANATO DE PESQUISA E INOVAÇÃO
EDITAL DPI/UnB Nº 04/2025 - PROGRAMA DE INICIAÇÃO CIENTÍFICA PIBIC/PIBITI 2025-2026
1. DO PROGRAMA
O Programa Institucional de Bolsas de Iniciação Científica (PIBIC) visa
despertar a vocação científica de estudantes de graduação da UnB,
oferecendo bolsas mensais do CNPq.
2. DOS REQUISITOS
"""


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def no_gemini_key(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")


@pytest.fixture
def gemini_key(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-test-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_SECONDS", 2.0)


def _gemini_payload(data) -> dict:
    """Monta uma resposta no formato oficial do endpoint generateContent."""
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}]}


def _install_mock_transport(monkeypatch, handler):
    """Substitui os clientes httpx do summarizer por clientes com MockTransport."""
    calls = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    transport = httpx.MockTransport(recording_handler)
    monkeypatch.setattr(
        summarizer, "_build_client", lambda timeout: httpx.Client(transport=transport, timeout=timeout)
    )
    monkeypatch.setattr(
        summarizer,
        "_build_async_client",
        lambda timeout: httpx.AsyncClient(transport=transport, timeout=timeout),
    )
    return calls


@pytest.fixture
def db_session(monkeypatch):
    import app.modules.scraper.pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod,
        "extract_pdf",
        lambda url, **kw: PDFDocumentExtraction(source=str(url), num_pages=1, full_text="", pages=[], tables=[]),
    )
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()


# ============================================================================
# Camada 1 — extrair_objeto_edital (Issue #77)
# ============================================================================


def test_extrair_objeto_secao_do_objeto_com_limpeza_sei():
    resumo = extrair_objeto_edital(TEXTO_EDITAL_TUTORES)
    assert resumo is not None
    assert resumo.startswith("O presente edital tem por objeto a seleção de tutores a distância")
    # Quebras de linha duras foram unidas e o ruído SEI/paginação removido
    assert "\n" not in resumo
    assert "SEI" not in resumo
    assert "Página" not in resumo
    assert "Processo nº" not in resumo
    # Não invade a próxima seção
    assert "INSCRIÇÕES" not in resumo
    assert len(resumo) <= 350


@pytest.mark.parametrize(
    "cabecalho",
    ["1. DO OBJETIVO", "1. DO PROGRAMA", "1. DA FINALIDADE", "1. DAS DISPOSIÇÕES PRELIMINARES", "I - DO OBJETO"],
)
def test_extrair_objeto_varias_secoes_unb(cabecalho):
    texto = (
        "UNIVERSIDADE DE BRASÍLIA\nDECANATO DE EXTENSÃO\n"
        f"{cabecalho}\n"
        "Selecionar projetos de extensão universitária que promovam a\n"
        "interação dialógica entre a UnB e a sociedade.\n"
        "2. DOS REQUISITOS\nSer estudante regular."
    )
    resumo = extrair_objeto_edital(texto)
    assert resumo == (
        "Selecionar projetos de extensão universitária que promovam a interação dialógica "
        "entre a UnB e a sociedade."
    )


def test_extrair_objeto_programa_pibic():
    resumo = extrair_objeto_edital(TEXTO_EDITAL_PIBIC)
    assert resumo is not None
    assert resumo.startswith("O Programa Institucional de Bolsas de Iniciação Científica (PIBIC)")
    assert "REQUISITOS" not in resumo


def test_extrair_objeto_limita_350_caracteres_em_fronteira():
    longo = "1. DO OBJETO\n" + " ".join(["Seleção de estudantes para bolsas de extensão universitária."] * 20)
    resumo = extrair_objeto_edital(longo)
    assert resumo is not None
    assert len(resumo) <= 350
    assert resumo.endswith(".") or resumo.endswith("…")


def test_extrair_objeto_texto_sem_secao_retorna_none():
    assert extrair_objeto_edital("Lista de presença da reunião ordinária do colegiado.") is None
    assert extrair_objeto_edital("") is None
    assert extrair_objeto_edital(None) is None  # type: ignore[arg-type]


def test_extrair_objeto_fallback_torna_publico():
    texto = (
        "O Decanato de Assuntos Comunitários torna pública a abertura de inscrições para o "
        "Auxílio Emergencial destinado a estudantes em situação de vulnerabilidade socioeconômica.\n"
        "Demais informações no site."
    )
    resumo = extrair_objeto_edital(texto)
    assert resumo is not None
    assert "Auxílio Emergencial" in resumo


def test_truncar_texto_respeita_limite():
    assert truncar_texto("Curto.", 350) == "Curto."
    out = truncar_texto("palavra " * 100, 50)
    assert len(out) <= 50
    assert not out.endswith(" ")


# ============================================================================
# Camada 1 — is_vague_title (Issue #106)
# ============================================================================


@pytest.mark.parametrize(
    "titulo",
    [
        None,
        "",
        "   ",
        ".",
        "S",
        "Nº",
        "AQUI",
        "Download",
        "EDITAL",
        "PIBIC",
        "PIBITI",
        "Nomeação",
        "Convocação",
        "Convocação para Entrevista",
        "Convocações",
        "Nomeações",
        "RESULTADO PRELIMINAR",
        "RESULTADO FINAL",
        "Resultado Provisório: AQUI",
        "Seleção de Tutores a Distância",
        "Seleção de Tutores Presenciais",
        "Processo de Seleção Simplificada",
        "Edital de Abertura",
        "Edital sem título",
        "Inscrições Abertas",
        "HE_UNB_22_2",
        "UNB_25_TF_DCS",
        "EDUCAMPO_25",
        "edital_monitoria_versao_final.pdf",
        "Resultado Final da Seleção",
        "Retificação do Edital",
        "JURAPP  - Edital",
        "JURAPP – Edital",
        "JURAPP – Inscrições abertas",
    ],
)
def test_is_vague_title_casos_reais(titulo):
    assert is_vague_title(titulo) is True


@pytest.mark.parametrize(
    "titulo",
    [
        "Edital Monitoria DEG 01/2026",
        "Edital DPG Nº 05/2026 - Mestrado em Computação",
        "Resultado Final do PIBIC 2024/2025",
        "Convocação para Entrevista - Edital Nº 158/2024",
        "Retificação do Edital de Monitoria",
        "Chamada de Extensão DEX 2026",
        "Edital Seleção Simplificada",
        "Processo Seletivo Transferência Facultativa 2025",
    ],
)
def test_is_vague_title_titulos_bons(titulo):
    assert is_vague_title(titulo) is False


# ============================================================================
# Camada 1 — reconstruir_titulo_edital (Issue #106)
# ============================================================================


def test_reconstruir_titulo_bom_nao_e_alterado():
    original = "  Edital Monitoria DEG 01/2026  "
    assert reconstruir_titulo_edital(original, texto_extraido=TEXTO_EDITAL_TUTORES) == "Edital Monitoria DEG 01/2026"


@pytest.mark.parametrize("lixo", [".", "S", "Nº", "AQUI", "Download", "EDITAL"])
def test_reconstruir_titulo_lixo_usa_cabecalho_do_texto(lixo):
    titulo = reconstruir_titulo_edital(lixo, texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD")
    assert not is_vague_title(titulo)
    assert "158/2024" in titulo
    assert "Tutores" in titulo
    assert "CEAD" in titulo
    # Lixo do título original não é preservado
    assert "Aqui" not in titulo and "Download" not in titulo
    assert len(titulo) <= 140


@pytest.mark.parametrize(
    "original, rotulo",
    [
        ("Convocação para Entrevista", "Convocação para Entrevista"),
        ("Convocações", "Convocações"),
        ("Nomeações", "Nomeações"),
        ("RESULTADO PRELIMINAR", "Resultado Preliminar"),
        ("RESULTADO FINAL", "Resultado Final"),
    ],
)
def test_reconstruir_titulo_preserva_rotulo_de_etapa(original, rotulo):
    titulo = reconstruir_titulo_edital(original, texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD")
    assert titulo.startswith(rotulo)
    assert "158/2024" in titulo
    assert not is_vague_title(titulo)


@pytest.mark.parametrize("programa", ["PIBIC", "PIBITI"])
def test_reconstruir_titulo_programa_com_assunto(programa):
    titulo = reconstruir_titulo_edital(
        programa,
        assunto="Iniciação Científica e Tecnológica 2025-2026",
        orgao_emissor="PROIC",
    )
    assert programa in titulo
    assert "Iniciação Científica" in titulo
    assert "PROIC" in titulo
    assert not is_vague_title(titulo)


def test_reconstruir_titulo_tutores_distancia_com_orgao():
    titulo = reconstruir_titulo_edital(
        "Seleção de Tutores a Distância",
        assunto="Edital CEAD",
        orgao_emissor="CEAD",
    )
    assert "Seleção de Tutores a Distância" in titulo
    assert "CEAD" in titulo
    assert not is_vague_title(titulo)


def test_reconstruir_titulo_codigo_tecnico_usa_nome_do_arquivo():
    titulo = reconstruir_titulo_edital(
        "HE_UNB_22_2",
        url_pdf="https://unb.br/images/Edital-Selecao%20Monitoria_Hospital_Escola.pdf",
        orgao_emissor="HUB",
    )
    assert "Monitoria" in titulo
    assert "Hospital Escola" in titulo
    assert "HUB" in titulo
    assert "%20" not in titulo and "_" not in titulo


def test_reconstruir_titulo_assunto_generico_e_longo_sao_higienizados():
    titulo = reconstruir_titulo_edital(".", assunto="Edital FUP", orgao_emissor="FUP")
    assert titulo.lower().count("edital") <= 1
    assert "FUP" in titulo

    assunto_tabela = "Seleção de bolsistas para o projeto de extensão " + "x " * 200
    titulo_longo = reconstruir_titulo_edital("AQUI", assunto=assunto_tabela, orgao_emissor="DEX")
    assert len(titulo_longo) <= 140
    assert "DEX" in titulo_longo


def test_reconstruir_titulo_title_case_preserva_siglas():
    texto = "EDITAL DEG/UNB Nº 12/2025 - SELEÇÃO DE MONITORES DO PROGRAMA PIBIC-AF E CNPQ"
    titulo = reconstruir_titulo_edital("EDITAL", texto_extraido=texto, orgao_emissor="DEG")
    assert "DEG/UnB" in titulo
    assert "Nº 12/2025" in titulo
    assert "PIBIC-AF" in titulo
    assert "CNPq" in titulo
    assert "Seleção de Monitores do Programa" in titulo


def test_reconstruir_titulo_sem_contexto_nunca_vazio():
    titulo = reconstruir_titulo_edital(".", orgao_emissor="DEG")
    assert titulo
    assert "DEG" in titulo
    assert reconstruir_titulo_edital(None)


# ============================================================================
# Camada 2 — summarizer.py (Gemini + Graceful Degradation)
# ============================================================================


def test_is_generic_summary():
    assert is_generic_summary(None)
    assert is_generic_summary("")
    assert is_generic_summary("Edital publicado pelo portal DEG em 2026-01-01.")
    assert is_generic_summary("Convocações", titulo="Convocações")
    assert not is_generic_summary(
        "Seleção de estudantes para monitoria das disciplinas de graduação do DEG.",
        titulo="Edital Monitoria",
    )


def test_sem_api_key_usa_camada_1_sem_chamar_http(no_gemini_key, monkeypatch):
    calls = _install_mock_transport(monkeypatch, lambda req: httpx.Response(500))

    titulo, resumo = enrich_title_and_summary(
        "AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )

    assert calls == []
    assert titulo == reconstruir_titulo_edital("AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD")
    assert resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)


def test_gemini_sucesso_titulo_e_resumo(gemini_key, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        assert request.headers["x-goog-api-key"] == "fake-test-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["temperature"] == 0.2
        prompt = body["contents"][0]["parts"][0]["text"]
        assert '"titulo"' in prompt and '"resumo"' in prompt
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Convocação para Entrevista - Seleção de Tutores a Distância UAB - Edital Nº 158/2024 (CEAD)",
                    "resumo": "Seleção de tutores a distância para cursos da UAB/UnB com bolsa CAPES. "
                    "Voltado a pós-graduandos e professores da rede pública.",
                }
            ),
        )

    calls = _install_mock_transport(monkeypatch, handler)
    titulo, resumo = enrich_title_and_summary(
        "Convocação para Entrevista", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )

    assert len(calls) == 1
    assert titulo.startswith("Convocação para Entrevista - Seleção de Tutores")
    assert resumo.startswith("Seleção de tutores a distância")


def test_gemini_sucesso_apenas_resumo_quando_titulo_bom(gemini_key, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        assert '"titulo"' not in prompt
        return httpx.Response(
            200,
            json=_gemini_payload({"resumo": "Bolsas PIBIC do CNPq para estudantes de graduação da UnB."}),
        )

    calls = _install_mock_transport(monkeypatch, handler)
    titulo, resumo = enrich_title_and_summary(
        "Edital DPI Nº 04/2025 - PIBIC/PIBITI", texto_extraido=TEXTO_EDITAL_PIBIC, orgao_emissor="DPI"
    )

    assert len(calls) == 1
    assert titulo == "Edital DPI Nº 04/2025 - PIBIC/PIBITI"
    assert resumo == "Bolsas PIBIC do CNPq para estudantes de graduação da UnB."


def test_gemini_nao_e_chamado_quando_titulo_e_resumo_ja_bons(gemini_key, monkeypatch):
    calls = _install_mock_transport(monkeypatch, lambda req: httpx.Response(500))
    titulo, resumo = enrich_title_and_summary(
        "Edital Monitoria DEG 01/2026",
        texto_extraido=TEXTO_EDITAL_TUTORES,
        resumo_atual="Seleção de monitores para disciplinas de graduação com bolsa de R$ 700,00.",
    )
    assert calls == []
    assert titulo == "Edital Monitoria DEG 01/2026"
    assert resumo == "Seleção de monitores para disciplinas de graduação com bolsa de R$ 700,00."


@pytest.mark.parametrize(
    "handler",
    [
        lambda req: httpx.Response(500, json={"error": "internal"}),
        lambda req: httpx.Response(429, json={"error": "quota"}),
        lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=req)),
        lambda req: (_ for _ in ()).throw(httpx.ConnectError("offline", request=req)),
        lambda req: httpx.Response(200, json=_gemini_payload("isso não é json")),
        lambda req: httpx.Response(200, json={"candidates": []}),
        lambda req: httpx.Response(200, json=_gemini_payload({"titulo": "AQUI", "resumo": ""})),
    ],
    ids=["http500", "http429", "timeout", "offline", "json_invalido", "sem_candidatos", "titulo_ainda_vago"],
)
def test_gemini_falha_cai_para_camada_1(gemini_key, monkeypatch, caplog, handler):
    _install_mock_transport(monkeypatch, handler)

    with caplog.at_level("WARNING"):
        titulo, resumo = enrich_title_and_summary(
            "AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
        )

    assert titulo == reconstruir_titulo_edital("AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD")
    assert resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)
    assert any(rec.levelname == "WARNING" for rec in caplog.records)


def test_gemini_resumo_e_titulo_sao_truncados(gemini_key, monkeypatch):
    longo = "Oportunidade de bolsa para estudantes da UnB com atividades de extensão. " * 15
    _install_mock_transport(
        monkeypatch,
        lambda req: httpx.Response(
            200, json=_gemini_payload({"titulo": "Seleção de Bolsistas de Extensão " * 10, "resumo": longo})
        ),
    )
    titulo, resumo = enrich_title_and_summary(".", texto_extraido=TEXTO_EDITAL_TUTORES)
    assert len(resumo) <= 350
    assert len(titulo) <= 140


def test_gemini_resposta_com_cerca_markdown(gemini_key, monkeypatch):
    texto_json = '```json\n{"resumo": "Seleção de tutores com bolsa CAPES para pós-graduandos."}\n```'
    _install_mock_transport(monkeypatch, lambda req: httpx.Response(200, json=_gemini_payload(texto_json)))
    _, resumo = enrich_title_and_summary("Edital CEAD Nº 158/2024 - Tutores", texto_extraido=TEXTO_EDITAL_TUTORES)
    assert resumo == "Seleção de tutores com bolsa CAPES para pós-graduandos."


def test_summarize_edital_retorna_apenas_resumo(no_gemini_key):
    assert summarize_edital("Edital CEAD 158/2024", texto_extraido=TEXTO_EDITAL_TUTORES) == extrair_objeto_edital(
        TEXTO_EDITAL_TUTORES
    )


@pytest.mark.asyncio
async def test_async_gemini_sucesso(gemini_key, monkeypatch):
    _install_mock_transport(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Resultado Final - Seleção de Tutores a Distância (CEAD)",
                    "resumo": "Resultado final da seleção de tutores a distância da UAB/UnB.",
                }
            ),
        ),
    )
    titulo, resumo = await enrich_title_and_summary_async(
        "RESULTADO FINAL", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert titulo == "Resultado Final - Seleção de Tutores a Distância (CEAD)"
    assert resumo == "Resultado final da seleção de tutores a distância da UAB/UnB."


@pytest.mark.asyncio
async def test_async_gemini_timeout_fallback(gemini_key, monkeypatch):
    def handler(req):
        raise httpx.ReadTimeout("timeout", request=req)

    _install_mock_transport(monkeypatch, handler)
    titulo, resumo = await enrich_title_and_summary_async(
        "AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert "158/2024" in titulo
    assert resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)


# ============================================================================
# Integração com upsert_edital (pipeline.py)
# ============================================================================


def test_upsert_novo_edital_titulo_vago_e_normalizado(db_session, no_gemini_key):
    from app.modules.scraper.pipeline import upsert_edital

    edital = upsert_edital(
        db=db_session,
        edital_data={
            "titulo": "AQUI",
            "link": "https://cead.unb.br/editais/158-2024",
            "orgao_emissor": "CEAD",
            "texto_extraido": TEXTO_EDITAL_TUTORES,
            "resumo": "Edital publicado pelo portal CEAD em 2024-10-01.",
        },
    )

    assert not is_vague_title(edital.titulo)
    assert "158/2024" in edital.titulo
    assert edital.resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)
    assert "Edital publicado pelo portal" not in edital.resumo


def test_upsert_nao_sobrescreve_resumo_informativo_com_generico(db_session, no_gemini_key):
    from app.modules.scraper.pipeline import upsert_edital

    resumo_bom = "Seleção de monitores para disciplinas de graduação com bolsa de R$ 700,00."
    payload = {
        "titulo": "Edital Monitoria DEG 01/2026",
        "link": "https://deg.unb.br/editais/monitoria-01-2026",
        "resumo": resumo_bom,
    }
    upsert_edital(db=db_session, edital_data=payload, enable_pdf_enrichment=False)

    reexec = upsert_edital(
        db=db_session,
        edital_data={**payload, "resumo": "Edital Monitoria DEG 01/2026"},
        enable_pdf_enrichment=False,
    )
    assert reexec.resumo == resumo_bom


def test_upsert_reprocessamento_idempotente_corrige_edital_existente_vago(db_session, no_gemini_key, monkeypatch):
    """Edital legado gravado com título vago é corrigido mesmo em reprocessamento redundante (sem baixar PDF)."""
    import app.modules.scraper.pipeline as pipeline_mod
    from app.modules.scraper.pipeline import _hash_edital, upsert_edital

    payload = {
        "titulo": "Convocações",
        "link": "https://cead.unb.br/editais/convocacoes-158",
        "url_pdf": "https://cead.unb.br/arquivos/convocacoes-158.pdf",
        "orgao_emissor": "CEAD",
    }
    hash_conteudo = _hash_edital(payload, [])

    # Simula registro legado (antes desta feature): título vago e resumo igual ao título
    legado = Edital(
        titulo="Convocações",
        url_pagina=payload["link"],
        url_pdf=payload["url_pdf"],
        orgao_emissor="CEAD",
        resumo="Convocações",
        texto_extraido=TEXTO_EDITAL_TUTORES,
        hash_conteudo=hash_conteudo,
        status_processamento="processado",
    )
    db_session.add(legado)
    db_session.commit()

    def fail_extract(*args, **kwargs):
        raise AssertionError("PDF não deve ser baixado novamente em reprocessamento redundante")

    monkeypatch.setattr(pipeline_mod, "extract_pdf", fail_extract)

    corrigido = upsert_edital(db=db_session, edital_data=payload)

    assert corrigido.id == legado.id
    assert corrigido.titulo.startswith("Convocações")
    assert "158/2024" in corrigido.titulo
    assert not is_vague_title(corrigido.titulo)
    assert corrigido.resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)
    assert corrigido.hash_conteudo == hash_conteudo

    # Terceira execução idêntica é estável (idempotente) e não volta ao título vago
    estavel = upsert_edital(db=db_session, edital_data=payload)
    assert estavel.titulo == corrigido.titulo
    assert estavel.resumo == corrigido.resumo


def test_upsert_nao_chama_llm_em_reprocessamento_de_edital_ja_normalizado(db_session, gemini_key, monkeypatch):
    from app.modules.scraper.pipeline import upsert_edital

    respostas = {"n": 0}

    def handler(req):
        respostas["n"] += 1
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Convocações - Seleção de Tutores a Distância - Edital Nº 158/2024 (CEAD)",
                    "resumo": "Seleção de tutores a distância da UAB/UnB com bolsa CAPES.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)
    payload = {
        "titulo": "Convocações",
        "link": "https://cead.unb.br/editais/convocacoes-llm",
        "orgao_emissor": "CEAD",
        "texto_extraido": TEXTO_EDITAL_TUTORES,
    }
    e1 = upsert_edital(db=db_session, edital_data=payload, enable_pdf_enrichment=False)
    assert respostas["n"] == 1
    assert e1.titulo.startswith("Convocações - Seleção de Tutores")
    assert e1.resumo == "Seleção de tutores a distância da UAB/UnB com bolsa CAPES."

    e2 = upsert_edital(db=db_session, edital_data=payload, enable_pdf_enrichment=False)
    assert respostas["n"] == 1
    assert e2.titulo == e1.titulo
    assert e2.resumo == e1.resumo


def test_sync_portal_nao_mascara_resumo_com_frase_generica(db_session, no_gemini_key, monkeypatch):
    """service.sync_portal_editais deixa o pipeline extrair o resumo real do texto_extraido."""
    from app.modules.scraper import service as service_mod

    class FakeScraper:
        orgao_origem = "CEAD"

        def fetch_editais(self, year=None):
            return [
                {
                    "titulo": "AQUI",
                    "link": "https://cead.unb.br/editais/fake-158",
                    "data_publicacao": "2024-10-01",
                    "texto_extraido": TEXTO_EDITAL_TUTORES,
                },
                {
                    "titulo": "Edital CEAD sem texto 01/2024",
                    "link": "https://cead.unb.br/editais/fake-sem-texto",
                    "data_publicacao": "2024-10-01",
                },
            ]

        def fetch_documentos(self, url):
            return []

    import app.modules.scraper as scraper_pkg

    monkeypatch.setattr(scraper_pkg, "get_scraper", lambda sigla: FakeScraper())
    monkeypatch.setattr(service_mod, "processar_notificacoes_se_configuradas", lambda db: None)

    service_mod.sync_portal_editais(db_session, "CEAD", max_items=10)

    com_texto = db_session.query(Edital).filter_by(url_pagina="https://cead.unb.br/editais/fake-158").one()
    assert com_texto.resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)
    assert "158/2024" in com_texto.titulo

    # Sem nenhum conteúdo extraível, mantém o fallback identificado como genérico
    sem_texto = db_session.query(Edital).filter_by(url_pagina="https://cead.unb.br/editais/fake-sem-texto").one()
    assert sem_texto.resumo.startswith("Edital publicado pelo portal CEAD")
    assert is_generic_summary(sem_texto.resumo, sem_texto.titulo)


# ============================================================================
# Backfill CLI (dry-run por padrão, --apply idempotente)
# ============================================================================


def test_backfill_dry_run_e_apply_idempotente(db_session, no_gemini_key):
    from app.modules.scraper.backfill_titles_summaries import run_backfill

    vago = Edital(
        titulo="RESULTADO FINAL",
        url_pagina="https://cead.unb.br/editais/rf-158",
        orgao_emissor="CEAD",
        resumo="Edital publicado pelo portal CEAD em 2024-10-01.",
        texto_extraido=TEXTO_EDITAL_TUTORES,
    )
    bom = Edital(
        titulo="Edital Monitoria DEG 01/2026",
        url_pagina="https://deg.unb.br/editais/monitoria-bf",
        resumo="Seleção de monitores para disciplinas de graduação com bolsa de R$ 700,00.",
    )
    db_session.add_all([vago, bom])
    db_session.commit()

    propostas = run_backfill(db_session)  # dry-run
    assert [m.edital_id for m in propostas] == [vago.id]
    db_session.refresh(vago)
    assert vago.titulo == "RESULTADO FINAL"

    aplicadas = run_backfill(db_session, apply=True)
    assert len(aplicadas) == 1
    db_session.refresh(vago)
    assert vago.titulo.startswith("Resultado Final")
    assert "158/2024" in vago.titulo
    assert vago.resumo == extrair_objeto_edital(TEXTO_EDITAL_TUTORES)

    assert run_backfill(db_session, apply=True) == []


# ============================================================================
# Regressões encontradas na verificação com dados reais do banco
# ============================================================================


def test_titulo_bom_longo_nunca_e_truncado(no_gemini_key):
    longo = (
        "Edital DEG Nº 70/2026 – Edital de Seleção Simplificada de Bolsistas – Licenciaturas em Movimento – "
        "Saberes em Rede 2026-2027 – Projeto Solos Negros: Práticas Territorializadas em Chão da Escola"
    )
    assert len(longo) > 140
    titulo, _ = enrich_title_and_summary(longo, texto_extraido="Texto sem seção reconhecível.")
    assert titulo == longo


def test_extrair_objeto_torna_publico_presente_instrumento():
    texto = (
        "O Decanato de Ensino de Graduação torna público o presente instrumento para a seleção simplificada "
        "de estudantes bolsistas no âmbito do Edital Licenciaturas em Movimento - Saberes em Rede 2025-2026. "
        "Outras disposições."
    )
    assert extrair_objeto_edital(texto) == (
        "Seleção simplificada de estudantes bolsistas no âmbito do Edital Licenciaturas em Movimento - "
        "Saberes em Rede 2025-2026."
    )
    texto2 = (
        "A Universidade de Brasília torna público o presente regulamento para a seleção de estudantes de "
        "graduação do PIBID, de acordo com os termos e dispositivos apresentados a seguir."
    )
    assert extrair_objeto_edital(texto2) == "Seleção de estudantes de graduação do PIBID."


def test_extrair_objeto_remove_cabecalho_composto_em_caixa_alta_e_numeracao_final():
    texto = (
        "1. DO OBJETO, HABILITAÇÃO E AVALIAÇÃO DAS PROPOSTAS\n"
        "Para concorrer ao Edital de Seleção de Projetos de Pesquisa e Extensão para atuação no CEIUnB, "
        "as proposições deverão estar alinhadas aos princípios institucionais. 4.\n"
        "2. DOS REQUISITOS\n"
    )
    resumo = extrair_objeto_edital(texto)
    assert resumo is not None
    assert resumo.startswith("Para concorrer ao Edital de Seleção de Projetos")
    assert "HABILITAÇÃO" not in resumo
    assert not resumo.endswith("4.")


def test_reconstruir_titulo_sigla_mais_generico_jurapp():
    t1 = reconstruir_titulo_edital(
        "JURAPP  - Edital",
        assunto="Grupos de Pesquisa / Iniciação Científica",
        orgao_emissor="DIREITO",
        url_pdf="http://www.direito.unb.br/images/JURAPP_Edital_2023.pdf",
    )
    assert t1 == "JURAPP - Grupos de Pesquisa / Iniciação Científica - DIREITO"
    assert not is_vague_title(t1)

    t2 = reconstruir_titulo_edital(
        "JURAPP – Inscrições abertas",
        assunto="Grupos de Pesquisa / Iniciação Científica",
        orgao_emissor="DIREITO",
    )
    assert t2 == "JURAPP - Inscrições Abertas - Grupos de Pesquisa / Iniciação Científica - DIREITO"
    assert not is_vague_title(t2)




# ============================================================================
# Issue #129 — Modelo padrão gemini-2.5-flash-lite, fallback 404 e retry 429
# ============================================================================


def test_config_padrao_gemini_2_5_flash_lite_e_fallback(monkeypatch):
    from app.core.config import Settings

    for var in ("GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "GEMINI_TIMEOUT_SECONDS", "GEMINI_RETRY_DELAY_SECONDS"):
        monkeypatch.delenv(var, raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.GEMINI_MODEL == "gemini-3.5-flash-lite"
    assert cfg.GEMINI_FALLBACK_MODEL == "gemini-flash-lite-latest"
    assert cfg.GEMINI_TIMEOUT_SECONDS == 15.0
    assert cfg.GEMINI_RETRY_DELAY_SECONDS == 2.0


def test_gemini_fallback_automatico_em_404_para_modelo_secundario(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODEL", "gemini-flash-latest")

    urls_chamadas = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls_chamadas.append(str(req.url))
        if "gemini-2.5-flash-lite" in str(req.url):
            return httpx.Response(404, json={"error": {"message": "Model not found"}})
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Edital Nº 158/2024 - Seleção de Tutores a Distância (CEAD)",
                    "resumo": "Seleção de tutores a distância para cursos da UAB/UnB com bolsa CAPES.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)
    titulo, resumo = enrich_title_and_summary(
        "AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert len(urls_chamadas) == 2
    assert "gemini-2.5-flash-lite" in urls_chamadas[0]
    assert "gemini-flash-latest" in urls_chamadas[1]
    assert titulo == "Edital Nº 158/2024 - Seleção de Tutores a Distância (CEAD)"
    assert resumo == "Seleção de tutores a distância para cursos da UAB/UnB com bolsa CAPES."


@pytest.mark.asyncio
async def test_async_gemini_fallback_automatico_em_404(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODEL", "gemini-flash-latest")

    urls_chamadas = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls_chamadas.append(str(req.url))
        if "gemini-2.5-flash-lite" in str(req.url):
            return httpx.Response(404, json={"error": {"message": "Model not found"}})
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Resultado Final - Seleção de Tutores a Distância (CEAD)",
                    "resumo": "Resultado final da seleção de tutores a distância da UAB/UnB.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)
    titulo, resumo = await enrich_title_and_summary_async(
        "RESULTADO FINAL", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert len(urls_chamadas) == 2
    assert "gemini-2.5-flash-lite" in urls_chamadas[0]
    assert "gemini-flash-latest" in urls_chamadas[1]
    assert titulo == "Resultado Final - Seleção de Tutores a Distância (CEAD)"
    assert resumo == "Resultado final da seleção de tutores a distância da UAB/UnB."


def test_gemini_retry_em_429_recupera_na_segunda_tentativa(gemini_key, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_RETRY_DELAY_SECONDS", 0.01)
    tentativas = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "Quota exceeded"}})
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Edital Nº 158/2024 - Seleção de Tutores a Distância (CEAD)",
                    "resumo": "Seleção de tutores a distância para a UAB/UnB com bolsa CAPES.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)
    titulo, resumo = enrich_title_and_summary(
        "AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert tentativas["n"] == 2
    assert titulo == "Edital Nº 158/2024 - Seleção de Tutores a Distância (CEAD)"
    assert resumo == "Seleção de tutores a distância para a UAB/UnB com bolsa CAPES."


def test_gemini_retry_em_503_recupera_na_segunda_tentativa(gemini_key, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_RETRY_DELAY_SECONDS", 0.01)
    tentativas = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            return httpx.Response(503, json={"error": {"message": "Service Unavailable"}})
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Edital Nº 158/2024 - Seleção de Tutores a Distância (CEAD)",
                    "resumo": "Seleção de tutores a distância para a UAB/UnB com bolsa CAPES.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)
    titulo, resumo = enrich_title_and_summary(
        "AQUI", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert tentativas["n"] == 2
    assert titulo == "Edital Nº 158/2024 - Seleção de Tutores a Distância (CEAD)"
    assert resumo == "Seleção de tutores a distância para a UAB/UnB com bolsa CAPES."


@pytest.mark.asyncio
async def test_async_gemini_retry_em_429_recupera_na_segunda_tentativa(gemini_key, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_RETRY_DELAY_SECONDS", 0.01)
    tentativas = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "Quota exceeded"}})
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Resultado Final - Seleção de Tutores a Distância (CEAD)",
                    "resumo": "Resultado final da seleção de tutores a distância da UAB/UnB.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)
    titulo, resumo = await enrich_title_and_summary_async(
        "RESULTADO FINAL", texto_extraido=TEXTO_EDITAL_TUTORES, orgao_emissor="CEAD"
    )
    assert tentativas["n"] == 2
    assert titulo == "Resultado Final - Seleção de Tutores a Distância (CEAD)"
    assert resumo == "Resultado final da seleção de tutores a distância da UAB/UnB."


def test_backfill_suporta_sleep_seconds_com_llm_ativo(db_session, gemini_key, monkeypatch):
    import app.modules.scraper.backfill_titles_summaries as bf_mod

    sleeps = []
    monkeypatch.setattr(bf_mod.time, "sleep", lambda s: sleeps.append(s))

    _install_mock_transport(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "titulo": "Resultado Final - Edital Nº 158/2024 - Tutores UAB (CEAD)",
                    "resumo": "Resultado final da seleção de tutores a distância da UAB/UnB.",
                }
            ),
        ),
    )

    vago = Edital(
        titulo="RESULTADO FINAL",
        url_pagina="https://cead.unb.br/editais/rf-sleep-test",
        orgao_emissor="CEAD",
        resumo="Edital publicado pelo portal CEAD em 2024-10-01.",
        texto_extraido=TEXTO_EDITAL_TUTORES,
    )
    db_session.add(vago)
    db_session.commit()

    mudancas = bf_mod.run_backfill(db_session, apply=True, sleep_seconds=1.5)
    assert len(mudancas) == 1
    assert sleeps == [1.5]


# ============================================================================
# Regressões: _TORNA_PUBLICO_RE ("os"/"as"), cronograma com "à" e upgrade Camada 1 -> 2
# ============================================================================


def test_extrair_objeto_torna_publicos_os_procedimentos_nao_corta_artigo():
    texto_os = (
        "1.1. A SDH, o DEG e o DAC tornam públicos os procedimentos que serão adotados para "
        "o preenchimento de vagas reservadas no CEI-UnB."
    )
    resumo_os = extrair_objeto_edital(texto_os)
    assert resumo_os is not None
    assert not resumo_os.startswith("S ")
    assert resumo_os.startswith("Procedimentos que serão adotados")

    texto_as = (
        "O Decanato de Extensão torna públicas as normas para submissão de projetos "
        "de extensão universitária na UnB."
    )
    resumo_as = extrair_objeto_edital(texto_as)
    assert resumo_as is not None
    assert not resumo_as.startswith("S ")
    assert resumo_as.startswith("Normas para submissão de projetos")


def test_parse_cronograma_cei_unb_com_crase_e_sem_ano():
    from datetime import datetime, timezone
    from app.modules.scraper.parser import parse_edital_metadados

    tabela = [
        ["Atividade", "Data"],
        ["Publicação do Edital", "19 de novembro"],
        ["Período de Inscrições", "19 de novembro à 4 de dezembro"],
        ["Análise das Inscrições", "7 à 11 de dezembro"],
        ["Resultado Preliminar", "14 de dezembro"],
        ["Resultado Final", "21 de dezembro"],
    ]
    doc = PDFDocumentExtraction(
        source="cei.pdf",
        num_pages=3,
        full_text="EDITAL SDH/DEG/DEX Nº 1/2026 - CEI-UnB",
        tables=[tabela],
    )
    meta = parse_edital_metadados(doc, ano_referencia=2026)
    assert meta.inicio_inscricao == datetime(2026, 11, 19, tzinfo=timezone.utc)
    assert meta.fim_inscricao == datetime(2026, 12, 4, tzinfo=timezone.utc)
    assert meta.data_resultado_preliminar == datetime(2026, 12, 14, tzinfo=timezone.utc)
    assert meta.data_resultado_final == datetime(2026, 12, 21, tzinfo=timezone.utc)


def test_upsert_e_backfill_fazem_upgrade_de_resumo_cortado_e_camada_1_para_gemini(
    db_session, gemini_key, monkeypatch
):
    import app.modules.scraper.backfill_titles_summaries as bf_mod
    from app.modules.scraper.pipeline import _hash_edital, upsert_edital
    from app.modules.scraper.summarizer import is_clipped_summary, is_weak_heuristic_summary

    assert is_clipped_summary("S procedimentos que serão adotados no CEI-UnB.") is True
    assert is_clipped_summary("A seleção de bolsistas para o projeto.") is False
    assert is_weak_heuristic_summary("O presente Edital tem por objeto selecionar pesquisadores.") is True
    assert is_weak_heuristic_summary("Seleção de bolsistas de graduação com bolsa de R$ 700,00.") is False

    chamadas = {"n": 0}

    def handler(req):
        chamadas["n"] += 1
        return httpx.Response(
            200,
            json=_gemini_payload(
                {
                    "resumo": "Seleção para preenchimento de vagas reservadas à comunidade acadêmica da UnB no CEI-UnB.",
                }
            ),
        )

    _install_mock_transport(monkeypatch, handler)

    texto_cei = (
        "1.1. A SDH, o DEG e o DAC tornam públicos os procedimentos que serão adotados para "
        "o preenchimento de vagas reservadas à Comunidade Acadêmica da UnB no CEI-UnB."
    )
    payload = {
        "titulo": "Edital SDH/DEG/DEX Nº 1/2026 – Vagas no CEI-UnB",
        "link": "https://deg.unb.br/editais/cei-unb-2026",
        "orgao_emissor": "DEG",
    }
    hash_conteudo = _hash_edital(payload, [])

    from datetime import date

    legado = Edital(
        titulo=payload["titulo"],
        url_pagina=payload["link"],
        orgao_emissor="DEG",
        resumo="S procedimentos que serão adotados para o preenchimento de vagas reservadas no CEI-UnB.",
        texto_extraido=texto_cei,
        inicio_inscricao=date(2026, 11, 19),
        fim_inscricao=date(2026, 12, 4),
        hash_conteudo=hash_conteudo,
        status_processamento="processado",
    )
    db_session.add(legado)
    db_session.commit()

    # Reprocessamento com Gemini ativo deve sobrescrever o resumo cortado da Camada 1
    atualizado = upsert_edital(db=db_session, edital_data=payload, enable_pdf_enrichment=False)
    assert chamadas["n"] == 1
    assert atualizado.resumo == (
        "Seleção para preenchimento de vagas reservadas à comunidade acadêmica da UnB no CEI-UnB."
    )

    # Nova execução com o resumo já melhorado pelo Gemini NÃO chama a API novamente
    estavel = upsert_edital(db=db_session, edital_data=payload, enable_pdf_enrichment=False)
    assert chamadas["n"] == 1
    assert estavel.resumo == atualizado.resumo

    # Backfill também detecta e faz upgrade de resumo bruto da Camada 1 ("O presente Edital...")
    bruto = Edital(
        titulo="Edital DEG/UnB Nº 76/2026 – Seleção de Pesquisadores",
        url_pagina="https://deg.unb.br/editais/deg-76-2026",
        orgao_emissor="DEG",
        resumo="O presente Edital tem por objeto selecionar pesquisadores para diagnósticos das licenciaturas.",
        texto_extraido="1. DO OBJETO\nO presente Edital tem por objeto selecionar pesquisadores.",
        inicio_inscricao=date(2026, 11, 19),
        fim_inscricao=date(2026, 11, 30),
    )
    db_session.add(bruto)
    db_session.commit()

    mudancas = bf_mod.run_backfill(db_session, apply=True)
    assert [m.edital_id for m in mudancas] == [bruto.id]
    assert chamadas["n"] == 2
    assert bf_mod.run_backfill(db_session, apply=True) == []
