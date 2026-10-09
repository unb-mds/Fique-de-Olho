"""Testes unitários para o módulo de parsing de metadados e prazos de editais."""

from datetime import datetime, timezone

from app.modules.scraper.parser import (
    EditalMetadados,
    detect_campus,
    detect_orgao_emissor,
    parse_data_interval,
    parse_edital_metadados,
)
from app.modules.scraper.pdf import PDFDocumentExtraction, PDFPageExtraction


def test_parse_data_interval_extenso():
    ini, fim = parse_data_interval("23 de setembro a 14 de outubro de 2026")
    assert ini == datetime(2026, 9, 23, tzinfo=timezone.utc)
    assert fim == datetime(2026, 10, 14, tzinfo=timezone.utc)


def test_parse_data_interval_mesmo_mes():
    ini, fim = parse_data_interval("10 a 25 de março de 2026")
    assert ini == datetime(2026, 3, 10, tzinfo=timezone.utc)
    assert fim == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_parse_data_interval_numerico():
    ini, fim = parse_data_interval("01/04/2026 a 15/04/2026")
    assert ini == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert fim == datetime(2026, 4, 15, tzinfo=timezone.utc)


def test_parse_data_interval_data_unica():
    ini, fim = parse_data_interval("11 de novembro de 2026")
    assert ini == datetime(2026, 11, 11, tzinfo=timezone.utc)
    assert fim == datetime(2026, 11, 11, tzinfo=timezone.utc)


def test_parse_data_interval_invalido():
    ini, fim = parse_data_interval("Não informado ou a definir")
    assert ini is None
    assert fim is None


def test_detect_orgao_emissor_multi_orgaos():
    assert detect_orgao_emissor("Decanato de Ensino de Graduação - DEG torna público...") == "DEG"
    assert detect_orgao_emissor("EDITAL DPG Nº 05/2026 - Pós-Graduação em Computação") == "DPG"
    assert detect_orgao_emissor("EDITAL CONJUNTO DEX/UnB - Projetos de Extensão Universitária") == "DEX"
    assert detect_orgao_emissor("Decanato de Pesquisa e Inovação (DPI) abre seleção...") == "DPI"
    assert detect_orgao_emissor("DAC - Decanato de Assuntos Comunitários - Auxílio Moradia") == "DAC"
    assert detect_orgao_emissor("Secretaria de Assuntos Internacionais (INT) - Mobilidade Acadêmica") == "INT"
    assert detect_orgao_emissor("Programa de Iniciação Científica PROIC UnB 2026") == "PROIC"
    assert detect_orgao_emissor("Diretoria de Acessibilidade (DACES) - Seleção de Apoio") == "DACES"
    assert detect_orgao_emissor("Biblioteca Central (BCE) - Bolsas de Apoio ao Acervo") == "BCE"


def test_detect_campus_multi_campi():
    assert detect_campus("As atividades ocorrerão na Faculdade do Gama (FGA).") == "FGA"
    assert detect_campus("Vagas destinadas à Faculdade de Ceilândia - FCE.") == "FCE"
    assert detect_campus("Curso sediado no Campus de Planaltina (FUP).") == "FUP"
    assert detect_campus("Aulas no Campus Darcy Ribeiro (Plano Piloto).") == "Darcy Ribeiro"
    assert detect_campus("Universidade de Brasília - Todos os campi.") == "Geral"


def test_parse_edital_metadados_from_tables():
    # Simula extração de PDF contendo uma tabela de cronograma
    tabela_cronograma = [
        ["Etapa", "Período (2026)"],
        ["Inscrições", "23 de setembro a 14 de outubro de 2026"],
        ["Resultado preliminar", "25 de outubro de 2026"],
        ["Divulgação do resultado final", "11 de novembro de 2026"],
    ]

    doc = PDFDocumentExtraction(
        source="edital_58_2026.pdf",
        num_pages=2,
        full_text="UNIVERSIDADE DE BRASÍLIA - DECANATO DE ENSINO DE GRADUAÇÃO (DEG)\nCampus Darcy Ribeiro. Vagas: 15 vagas com bolsa remunerada de R$ 700,00.",
        tables=[tabela_cronograma],
        pages=[
            PDFPageExtraction(
                index=1,
                text="UNIVERSIDADE DE BRASÍLIA - DEG. 15 vagas. Bolsa de R$ 700,00.",
                tables=[tabela_cronograma],
            )
        ],
    )

    metadados = parse_edital_metadados(doc)

    assert isinstance(metadados, EditalMetadados)
    assert metadados.orgao_emissor == "DEG"
    assert metadados.campus == "Darcy Ribeiro"
    assert metadados.vagas == 15
    assert metadados.bolsa_remunerada is True
    assert metadados.valor_bolsa == 700.0
    assert metadados.inicio_inscricao == datetime(2026, 9, 23, tzinfo=timezone.utc)
    assert metadados.fim_inscricao == datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert metadados.data_resultado_preliminar == datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert metadados.data_resultado_final == datetime(2026, 11, 11, tzinfo=timezone.utc)
    assert len(metadados.cronograma) == 3


def test_parse_edital_metadados_text_fallback():
    # Sem tabelas, com datas no corpo do texto
    texto = """
    UNIVERSIDADE DE BRASÍLIA
    DECANATO DE PÓS-GRADUAÇÃO - DPG
    EDITAL DE SELEÇÃO MESTRADO 2026 - FGA (Campus Gama)
    Total de 8 vagas.
    Inscrições: de 01/10/2026 a 20/10/2026 através do SIGAA.
    """

    metadados = parse_edital_metadados(texto)

    assert metadados.orgao_emissor == "DPG"
    assert metadados.campus == "FGA"
    assert metadados.vagas == 8
    assert metadados.inicio_inscricao == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert metadados.fim_inscricao == datetime(2026, 10, 20, tzinfo=timezone.utc)


def test_parse_edital_metadados_graceful_defaults():
    # Texto sem datas nem termos específicos retorna None com segurança
    texto_vazio = "Documento administrativo genérico sem cronograma específico."

    metadados = parse_edital_metadados(texto_vazio)

    assert metadados.orgao_emissor is None
    assert metadados.campus is None
    assert metadados.inicio_inscricao is None
    assert metadados.fim_inscricao is None
    assert metadados.vagas is None
    assert metadados.bolsa_remunerada is None
    assert metadados.cronograma == []
