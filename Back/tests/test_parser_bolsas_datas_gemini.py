"""Testes unitários e de integração para a Issue #121:
- Refinamento de detecção de bolsas (evitar taxas de inscrição e orçamentos globais).
- Expansão de padrões de datas (horários limites, formatos abreviados, dias úteis).
- Fallback inteligente com Gemini (Camada 2 - LLM) para preencher metadados ausentes.
- Suporte a orgao_emissor / orgaoEmissor na serialização de editais.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.core.database import Edital, StatusEdital
from app.modules.editais.service import serialize_edital
from app.modules.scraper.parser import (
    detect_bolsa,
    parse_data_interval,
    parse_edital_metadados,
)
from app.modules.scraper.summarizer import enrich_metadata_with_llm


# ---------------------------------------------------------------------------
# 1. Detecção Contextual de Bolsas (Camada 1)
# ---------------------------------------------------------------------------


def test_detect_bolsa_ignora_taxa_de_inscricao():
    """Valida que taxas de inscrição não são interpretadas como bolsas."""
    texto = "O valor da taxa de inscrição é de R$ 50,00, a ser recolhida via Guia de Recolhimento da União (GRU)."
    tem_bolsa, valor = detect_bolsa(texto)
    assert valor is None
    assert tem_bolsa is not True


def test_detect_bolsa_ignora_orcamento_global():
    """Valida que orçamentos globais de projetos não são interpretados como bolsas de estudante."""
    texto = "O projeto contará com orçamento global aprovado de R$ 350.000,00 financiado pela FAPDF."
    tem_bolsa, valor = detect_bolsa(texto)
    assert valor is None
    assert tem_bolsa is not True


def test_detect_bolsa_captura_bolsa_mesmo_com_taxa_presente():
    """Garante que a presença de taxa não impede a captura da bolsa real descrita no edital."""
    texto = (
        "Será cobrada taxa de inscrição no valor de R$ 40,00. "
        "O candidato aprovado fará jus a uma bolsa mensal remunerada no valor de R$ 700,00 durante 12 meses."
    )
    tem_bolsa, valor = detect_bolsa(texto)
    assert tem_bolsa is True
    assert valor == 700.0


def test_detect_bolsa_auxilio_financeiro():
    """Captura auxílio financeiro ou remuneração estipulada em reais."""
    texto = "Será concedido auxílio financeiro mensal de R$ 400,00 aos discentes participantes."
    tem_bolsa, valor = detect_bolsa(texto)
    assert tem_bolsa is True
    assert valor == 400.0


def test_detect_bolsa_qualitativa_sem_valor():
    """Identifica menção a bolsas institucionais mesmo sem valor monetário expresso."""
    texto = "O projeto contemplará concessão de bolsa de pesquisa PIBIC/CNPq de acordo com as normas vigentes."
    tem_bolsa, valor = detect_bolsa(texto)
    assert tem_bolsa is True
    assert valor is None


def test_detect_bolsa_voluntario_sem_remuneracao():
    """Identifica quando a oportunidade é explicitamente não remunerada ou voluntária."""
    texto = "A seleção destina-se ao preenchimento de vagas para atuação como monitor voluntário, sem remuneração."
    tem_bolsa, valor = detect_bolsa(texto)
    assert tem_bolsa is False
    assert valor is None


# ---------------------------------------------------------------------------
# 2. Expansão dos Padrões de Prazos e Datas (Camada 1)
# ---------------------------------------------------------------------------


def test_parse_data_interval_limite_com_horario_extenso():
    """Trata expressões do tipo 'até às 18h do dia 15 de dezembro de 2026'."""
    ini, fim = parse_data_interval("As inscrições serão aceitas até às 18h do dia 15 de dezembro de 2026.")
    assert fim == datetime(2026, 12, 15, tzinfo=timezone.utc)


def test_parse_data_interval_limite_com_horario_numerico():
    """Trata expressões do tipo 'inscrições até 23:59 do dia 20/11/2026'."""
    ini, fim = parse_data_interval("Inscrições até 23:59 do dia 20/11/2026.")
    assert fim == datetime(2026, 11, 20, tzinfo=timezone.utc)


def test_parse_data_interval_abreviado_barra():
    """Trata formato '02 a 06/03/2026'."""
    ini, fim = parse_data_interval("Período de inscrições: 02 a 06/03/2026.")
    assert ini == datetime(2026, 3, 2, tzinfo=timezone.utc)
    assert fim == datetime(2026, 3, 6, tzinfo=timezone.utc)


def test_parse_data_interval_mes_abreviado():
    """Trata formato '05 a 12 de mar de 2026'."""
    ini, fim = parse_data_interval("Inscrições abertas de 05 a 12 de mar de 2026.")
    assert ini == datetime(2026, 3, 5, tzinfo=timezone.utc)
    assert fim == datetime(2026, 3, 12, tzinfo=timezone.utc)


def test_parse_edital_metadados_prazo_relativo_dias_uteis():
    """Calcula prazo final quando o texto estipula dias úteis a contar da publicação."""
    texto = (
        "EDITAL DEG Nº 01/2026\n"
        "As inscrições ficarão abertas pelo período de 10 dias úteis a contar da data de publicação."
    )
    # 2026-10-01 é quinta-feira. 10 dias úteis caem em 2026-10-15 (quinta-feira)
    dt_pub = datetime(2026, 10, 1, tzinfo=timezone.utc)
    metadados = parse_edital_metadados(texto, data_publicacao=dt_pub)
    assert metadados.fim_inscricao is not None
    assert metadados.fim_inscricao.date() == date(2026, 10, 15)


# ---------------------------------------------------------------------------
# 3. Fallback com Gemini (Camada 2 - LLM)
# ---------------------------------------------------------------------------


def test_enrich_metadata_with_llm_success(monkeypatch):
    """Verifica que o Gemini preenche início, fim de inscrição e valor de bolsa quando mockado."""
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "fake-test-key")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"inicio_inscricao": "2026-11-01", '
                                '"fim_inscricao": "2026-11-20", '
                                '"valor_bolsa": 700.0, '
                                '"tem_bolsa": true, '
                                '"vagas": 6, '
                                '"orgao_emissor": "DEG"}'
                            )
                        }
                    ]
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        resultado = enrich_metadata_with_llm(
            texto_extraido="Texto do edital com processo de monitoria...",
            titulo="Edital de Monitoria",
        )

    assert resultado.get("inicio_inscricao") == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert resultado.get("fim_inscricao") == datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert resultado.get("valor_bolsa") == 700.0
    assert resultado.get("vagas") == 6
    assert resultado.get("orgao_emissor") == "DEG"


def test_enrich_metadata_with_llm_graceful_failure(monkeypatch):
    """Garante que qualquer erro na chamada do Gemini não levanta exceção e retorna dict vazio."""
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "fake-test-key")

    with patch("httpx.Client.post", side_effect=Exception("Timeout no Gemini")):
        resultado = enrich_metadata_with_llm(
            texto_extraido="Texto do edital...",
            titulo="Edital DEG",
        )

    assert resultado == {}


def test_enrich_metadata_with_llm_sem_api_key(monkeypatch):
    """Sem GEMINI_API_KEY, a função retorna silenciosamente sem fazer requisição."""
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    resultado = enrich_metadata_with_llm(texto_extraido="Texto qualquer...", titulo="Edital")
    assert resultado == {}


# ---------------------------------------------------------------------------
# 4. Serialização do Órgão Emissor para os Cards
# ---------------------------------------------------------------------------


def test_serialize_edital_fornece_orgao_emissor_e_camelcase():
    """Garante que tanto orgao_emissor quanto orgaoEmissor são entregues para consumo dos cards."""
    edital = Edital(
        id=42,
        titulo="Edital de Bolsas de Extensão",
        orgao_emissor="DEX",
        campus="Darcy Ribeiro",
        tipo="Extensão",
        status=StatusEdital.ABERTO,
    )
    dados = serialize_edital(edital)
    assert dados["orgao_emissor"] == "DEX"
    assert dados["orgaoEmissor"] == "DEX"
