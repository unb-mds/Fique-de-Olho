from datetime import date, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, TipoDocumento, get_db
from app.main import app
from app.modules.editais.service import (
    _consultar_stats_editais,
    list_editais_com_filtros,
    serialize_edital,
)


@pytest.fixture
def db_session_editais():
    """Cria banco SQLite em memória com múltiplos editais para testar filtros."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    prazo_futuro = date.today() + timedelta(days=30)

    # Cria editais variados de diferentes anos e títulos
    e1 = Edital(
        id=1,
        titulo="Edital Monitoria DEG 01/2026",
        url_pagina="https://deg.unb.br/editais/monitoria-2026",
        campus="Darcy Ribeiro",
        tipo="monitoria",
        data_publicacao=datetime(2026, 3, 15),
        fim_inscricao=prazo_futuro,
        status=StatusEdital.ABERTO,
    )
    doc1 = EditalDocumento(
        id=1,
        edital_id=1,
        url_pdf="https://deg.unb.br/docs/monitoria.pdf",
        tipo_documento=TipoDocumento.ORIGINAL,
    )

    e2 = Edital(
        id=2,
        titulo="Processo Seletivo Transferência Facultativa 2025",
        url_pagina="https://deg.unb.br/editais/transferencia-2025",
        campus="FGA",
        tipo="transferencia",
        data_publicacao=datetime(2025, 6, 20),
        status=StatusEdital.ENCERRADO,
    )

    e3 = Edital(
        id=3,
        titulo="Edital de Estágio Não Obrigatório 2026",
        url_pagina="https://deg.unb.br/editais/estagio-2026",
        campus="Darcy Ribeiro",
        tipo="estagio",
        data_publicacao=datetime(2026, 8, 10),
        fim_inscricao=prazo_futuro,
        status=StatusEdital.ABERTO,
    )

    session.add_all([e1, doc1, e2, e3])
    session.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client_editais(db_session_editais):
    with TestClient(app) as test_client:
        yield test_client


def test_list_editais_sem_filtro_retorna_todos(client_editais):
    response = client_editais.get("/editais/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    # Verifica que o primeiro tem documento vinculado
    edital_1 = next(e for e in data if e["id"] == 1)
    assert len(edital_1["documentos"]) == 1
    assert edital_1["documentos"][0]["tipo_documento"] == "original"


def test_list_editais_filtro_por_ano(client_editais):
    # Filtra por 2025: deve retornar apenas o e2
    response = client_editais.get("/editais/?ano=2025")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2
    assert "2025" in data[0]["titulo"]

    # Filtra por 2026: deve retornar e1 e e3
    response_2026 = client_editais.get("/editais/?ano=2026")
    assert response_2026.status_code == 200
    data_2026 = response_2026.json()
    assert len(data_2026) == 2


def test_list_editais_filtro_por_busca_texto_q(client_editais):
    # Busca case-insensitive "monitoria"
    response = client_editais.get("/editais/?q=MONITORIA")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1


def test_list_editais_filtro_combinado_ano_e_busca(client_editais):
    # Busca "edital" no ano 2026: retorna e1 e e3
    response = client_editais.get("/editais/?ano=2026&q=edital")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Busca "transferência" no ano 2026: não existe em 2026
    response_vazia = client_editais.get("/editais/?ano=2026&q=transferência")
    assert response_vazia.status_code == 200
    assert response_vazia.json() == []


def test_list_editais_termo_inexistente(client_editais):
    response = client_editais.get("/editais/?q=termo_completamente_inexistente")
    assert response.status_code == 200
    assert response.json() == []


def test_list_editais_prefix_api_v1(client_editais):
    response = client_editais.get("/api/v1/editais/?ano=2025")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_list_editais_filtro_por_situacao(client_editais):
    abertos = client_editais.get("/api/v1/editais/?status=aberto")
    encerrados = client_editais.get("/api/v1/editais/?status=fechado")

    assert abertos.status_code == 200
    assert encerrados.status_code == 200
    assert {item["id"] for item in abertos.json()} == {1, 3}
    assert {item["id"] for item in encerrados.json()} == {2}


def test_editais_stats_retorna_contagens_reais(client_editais):
    response = client_editais.get("/api/v1/editais/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "abertos": 2,
        "encerrados": 1,
    }


def _make_isolated_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_filtro_graduacao_nao_retorna_pos_graduacao():
    """Ao filtrar por Graduação, editais de Pós-graduação (mestrado/doutorado/DPG/PPG) nunca podem vazar."""
    db = _make_isolated_session()
    try:
        hoje = date.today()
        db.add_all([
            Edital(
                id=10,
                titulo="Edital DEG/UnB Nº 76/2026 – Diagnósticos sobre Licenciaturas",
                url_pagina="https://deg.unb.br/edital-76-2026",
                orgao_emissor="DEG",
                assunto=None,
                data_publicacao=datetime(hoje.year, hoje.month, hoje.day),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=11,
                titulo="Edital de Monitoria de Graduação 2026",
                url_pagina="https://deg.unb.br/monitoria-grad-2026",
                orgao_emissor="DEG",
                resumo="Seleção de estudantes de graduação para monitoria.",
                data_publicacao=datetime(hoje.year, hoje.month, hoje.day),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=12,
                titulo="Programa de Pós-Graduação em Física Edital 5/2026 - DOUTORADO",
                url_pagina="https://sigaa.unb.br/fisica-doutorado",
                orgao_emissor="SIGAA",
                resumo="Edital de seleção para cursos de pós-graduação stricto sensu.",
                assunto="Processo Seletivo de Pós-Graduação (Mestrado/Doutorado)",
                data_publicacao=datetime(hoje.year, hoje.month, hoje.day),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=13,
                titulo="Seleção de Mestrado em Zoologia - Edital 2027.1",
                url_pagina="https://sigaa.unb.br/zoologia-mestrado",
                orgao_emissor="SIGAA",
                resumo="Edital de seleção para cursos de pós-graduação stricto sensu.",
                data_publicacao=datetime(hoje.year, hoje.month, hoje.day),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=14,
                titulo="Edital de Pós Graduação Lato Sensu em Gestão Pública",
                url_pagina="https://dpg.unb.br/lato-sensu",
                orgao_emissor="DPG",
                data_publicacao=datetime(hoje.year, hoje.month, hoje.day),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=15,
                titulo="Edital 01/2026 - PPGCA",
                url_pagina="https://sigaa.unb.br/ppgca",
                orgao_emissor="PPGCONT",
                resumo="Seleção para egressos de graduação interessados no programa.",
                data_publicacao=datetime(hoje.year, hoje.month, hoje.day),
                status=StatusEdital.ABERTO,
            ),
        ])
        db.commit()

        grad = list_editais_com_filtros(db, categoria="Graduação")
        assert {e.id for e in grad} == {10, 11}
        assert all(serialize_edital(e)["categoria"] != "Pós-graduação" for e in grad)

        pos = list_editais_com_filtros(db, categoria="Pós-graduação")
        assert {e.id for e in pos} == {12, 13, 14, 15}
        assert all(serialize_edital(e)["categoria"] == "Pós-graduação" for e in pos)
    finally:
        db.close()


def test_filtro_abertos_intercambio_exclui_antigos_e_encerrados():
    """Editais abertos de Intercâmbio não devem incluir editais antigos sem prazo nem já finalizados."""
    db = _make_isolated_session()
    try:
        hoje = date.today()
        recente = hoje - timedelta(days=10)
        antigo_meses = hoje - timedelta(days=180)

        e_aberto_prazo = Edital(
            id=20,
            titulo="Edital INT N. 12/2026 – Programa de Intercâmbio Internacional",
            url_pagina="https://int.unb.br/edital-12-2026",
            orgao_emissor="INT",
            data_publicacao=datetime(antigo_meses.year, antigo_meses.month, antigo_meses.day),
            fim_inscricao=hoje + timedelta(days=15),
            status=StatusEdital.ABERTO,
        )
        e_aberto_recente = Edital(
            id=21,
            titulo="Edital INT N. 15/2026",
            url_pagina="https://int.unb.br/edital-15-2026",
            orgao_emissor="INT",
            resumo="Pré-seleção para mobilidade acadêmica internacional.",
            data_publicacao=datetime(recente.year, recente.month, recente.day),
            fim_inscricao=None,
            status=StatusEdital.ABERTO,
        )
        e_antigo_2024 = Edital(
            id=22,
            titulo="EDITAL DE INTERCÂMBIO FÓRUNS EJA",
            url_pagina="https://fup.unb.br/intercambio-2024",
            orgao_emissor="FUP",
            data_publicacao=datetime(2024, 1, 15),
            fim_inscricao=None,
            status=StatusEdital.ABERTO,
        )
        e_antigo_sem_prazo = Edital(
            id=23,
            titulo="EDITAL FAV/MARCA N°010/2026 — Mobilidade Acadêmica",
            url_pagina="https://fav.unb.br/marca-2026",
            orgao_emissor="FAL",
            data_publicacao=datetime(antigo_meses.year, antigo_meses.month, antigo_meses.day),
            fim_inscricao=None,
            status=StatusEdital.ABERTO,
        )
        e_com_resultado_final = Edital(
            id=24,
            titulo="EDITAL INT N. 9/2026 – Intercâmbio SUSI",
            url_pagina="https://int.unb.br/edital-9-2026",
            orgao_emissor="INT",
            data_publicacao=datetime(recente.year, recente.month, recente.day),
            fim_inscricao=None,
            status=StatusEdital.ABERTO,
        )
        e_com_resultado_final.documentos.append(
            EditalDocumento(
                url_pdf="https://sei.unb.br/sei/publicacoes/resultado-final-9",
                tipo_documento=TipoDocumento.RESULTADO_FINAL,
            )
        )
        e_estagio_int = Edital(
            id=25,
            titulo="Edital Nº 2/INT/2026 – ESTÁGIO PRESENCIAL NA SECRETARIA DE ASSUNTOS INTERNACIONAIS",
            url_pagina="https://int.unb.br/estagio-int-2026",
            orgao_emissor="INT",
            data_publicacao=datetime(recente.year, recente.month, recente.day),
            fim_inscricao=hoje + timedelta(days=20),
            status=StatusEdital.ABERTO,
        )

        db.add_all([
            e_aberto_prazo,
            e_aberto_recente,
            e_antigo_2024,
            e_antigo_sem_prazo,
            e_com_resultado_final,
            e_estagio_int,
        ])
        db.commit()

        abertos = list_editais_com_filtros(db, status="aberto", categoria="Intercâmbio")
        assert {e.id for e in abertos} == {20, 21}
        assert all(serialize_edital(e)["status"] == "aberto" for e in abertos)

        fechados = list_editais_com_filtros(db, status="fechado", categoria="Intercâmbio")
        assert {e.id for e in fechados} == {22, 23, 24}
        assert all(serialize_edital(e)["status"] == "fechado" for e in fechados)

        stats = _consultar_stats_editais(db)
        assert stats == {"total": 6, "abertos": 3, "encerrados": 3}
    finally:
        db.close()


def test_filtro_campus_resolve_aliases_sigla_e_nome():
    """Filtrar por 'FGA (Gama)' ou 'FUP (Planaltina)' deve encontrar registros salvos por sigla ou nome."""
    db = _make_isolated_session()
    try:
        db.add_all([
            Edital(
                id=30,
                titulo="Edital FGA 2026",
                url_pagina="https://fga.unb.br/edital-1",
                campus="FGA",
                data_publicacao=datetime(2026, 10, 1),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=31,
                titulo="Edital Gama 2026",
                url_pagina="https://fga.unb.br/edital-2",
                campus="Gama",
                data_publicacao=datetime(2026, 10, 2),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=32,
                titulo="Edital FUP Planaltina",
                url_pagina="https://fup.unb.br/edital-1",
                campus="Planaltina",
                data_publicacao=datetime(2026, 10, 3),
                status=StatusEdital.ABERTO,
            ),
        ])
        db.commit()

        gama = list_editais_com_filtros(db, campus="FGA (Gama)")
        assert {e.id for e in gama} == {30, 31}

        planaltina = list_editais_com_filtros(db, campus="FUP (Planaltina)")
        assert {e.id for e in planaltina} == {32}
    finally:
        db.close()


def test_filtro_campus_gama_e_ceilandia_reconhece_fcte_fcts_e_mencoes_no_texto():
    """Editais que citam FGA/FCTE (Gama) ou FCE/FCTS (Ceilândia) no título/resumo devem aparecer mesmo com campus legado."""
    from app.modules.scraper.parser import detect_campus

    assert detect_campus("Edital FCTE/UnB - Campus Gama. Rodapé: Campus Universitário Darcy Ribeiro, Asa Norte.") == "FGA"
    assert detect_campus("Seleção na Faculdade de Ciências e Tecnologias em Saúde (FCTS).") == "FCE"
    assert detect_campus("Vagas para todos os campi da Universidade de Brasília.") == "Geral"
    assert detect_campus("Vagas na FGA e na FCE para estudantes da UnB.") == "Geral"

    db = _make_isolated_session()
    try:
        db.add_all([
            Edital(
                id=40,
                titulo="Edital de Monitoria FCTE - Campus Gama 2026",
                url_pagina="https://deg.unb.br/edital-fcte-gama",
                campus="Darcy Ribeiro",
                data_publicacao=datetime(2026, 10, 1),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=41,
                titulo="Seleção de Bolsistas da Faculdade de Ciências e Tecnologias em Saúde (FCTS)",
                url_pagina="https://deg.unb.br/edital-fcts-ceilandia",
                campus="Darcy Ribeiro",
                resumo="Oportunidade para estudantes do Campus Ceilândia.",
                data_publicacao=datetime(2026, 10, 2),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=42,
                titulo="Edital FCE 02/2026",
                url_pagina="https://sigaa.unb.br/edital-fce",
                campus="FCE",
                data_publicacao=datetime(2026, 10, 3),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=43,
                titulo="Edital com ampla gama de projetos no Plano Piloto",
                url_pagina="https://deg.unb.br/edital-darcy",
                campus="Darcy Ribeiro",
                data_publicacao=datetime(2026, 10, 4),
                status=StatusEdital.ABERTO,
            ),
        ])
        db.commit()

        gama = list_editais_com_filtros(db, campus="FGA (Gama)")
        assert {e.id for e in gama} == {40}

        ceilandia = list_editais_com_filtros(db, campus="FCE (Ceilândia)")
        assert {e.id for e in ceilandia} == {41, 42}
    finally:
        db.close()


def test_filtro_ano_inclui_editais_do_ano_seguinte_por_inscricao_ou_titulo():
    """Filtrar pelo próximo ano deve encontrar editais publicados no fim do ano anterior com prazo ou referência ao ano seguinte."""
    db = _make_isolated_session()
    try:
        db.add_all([
            Edital(
                id=50,
                titulo="Seleção de Mestrado em Computação - Ingresso 2027.1",
                url_pagina="https://dpg.unb.br/mestrado-2027",
                data_publicacao=datetime(2026, 11, 20),
                fim_inscricao=date(2026, 12, 15),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=51,
                titulo="Edital de Bolsas de Verão",
                url_pagina="https://dex.unb.br/verao",
                data_publicacao=datetime(2026, 11, 22),
                fim_inscricao=date(2027, 1, 20),
                status=StatusEdital.ABERTO,
            ),
            Edital(
                id=52,
                titulo="Edital Encerrado 2025",
                url_pagina="https://deg.unb.br/antigo-2025",
                data_publicacao=datetime(2025, 5, 10),
                fim_inscricao=date(2025, 5, 30),
                status=StatusEdital.ENCERRADO,
            ),
        ])
        db.commit()

        editais_2027 = list_editais_com_filtros(db, ano=2027)
        assert {e.id for e in editais_2027} == {50, 51}
    finally:
        db.close()
