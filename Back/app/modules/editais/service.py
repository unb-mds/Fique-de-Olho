"""Camada de serviço para operações de banco de dados do módulo de Editais."""

from datetime import date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.modules.editais.models import Edital, Campus, TipoEdital


def serialize_edital(edital: Edital, detail: bool = False) -> Dict[str, Any]:
    """Serializa uma entidade Edital para formato compatível com o schema e o frontend."""
    today = date.today()

    if edital.fim_inscricao:
        status_edital = "aberto" if edital.fim_inscricao >= today else "fechado"
    else:
        status_edital = "aberto"

    campus_nome = edital.campi[0].nome if edital.campi else "Geral"
    tipo_nome = edital.tipos[0].nome if edital.tipos else "Geral"

    dt_pub_iso = edital.data_publicacao.isoformat() if edital.data_publicacao else None
    dt_fim_iso = edital.fim_inscricao.isoformat() if edital.fim_inscricao else None

    resumo_texto = edital.resumo or "Processo seletivo publicado pela Universidade de Brasília."

    data: Dict[str, Any] = {
        "id": edital.id,
        "titulo": edital.titulo,
        "status": status_edital,
        "resumo": resumo_texto,
        "descricao": resumo_texto,
        "campus": campus_nome,
        "unidade": campus_nome,
        "categoria": tipo_nome,
        "data_publicacao": edital.data_publicacao,
        "dataPublicacao": dt_pub_iso,
        "inicio_inscricao": edital.inicio_inscricao,
        "fim_inscricao": edital.fim_inscricao,
        "prazoFinal": dt_fim_iso,
        "url_pdf": edital.url_pdf,
        "urlDocumento": edital.url_pdf,
        "status_processamento": edital.status_processamento or "processado",
        "vagas": None,
        "valor": None,
        "campi": [{"id": c.id, "nome": c.nome} for c in edital.campi],
        "tipos": [{"id": t.id, "nome": t.nome} for t in edital.tipos],
    }

    if detail:
        data.update({
            "identificador_origem": edital.identificador_origem,
            "texto_extraido": edital.texto_extraido,
            "hash_conteudo": edital.hash_conteudo,
            "criado_em": edital.criado_em,
            "atualizado_em": edital.atualizado_em,
        })

    return data


def seed_initial_editais(db: Session) -> None:
    """Popula dados iniciais de catálogo e editais de demonstração caso o banco esteja vazio."""
    # 1. Catálogos de Campi
    campi_nomes = ["Darcy Ribeiro", "FGA", "FCE", "FUP", "Geral"]
    campi_map: Dict[str, Campus] = {}
    for nome in campi_nomes:
        c = db.query(Campus).filter(Campus.nome == nome).first()
        if not c:
            c = Campus(nome=nome)
            db.add(c)
            db.flush()
        campi_map[nome] = c

    # 2. Catálogos de Tipos
    tipos_nomes = ["Monitoria", "Bolsas / Auxílios", "Extensões", "PIBIC", "Estágio", "Pesquisa", "Vestibular"]
    tipos_map: Dict[str, TipoEdital] = {}
    for nome in tipos_nomes:
        t = db.query(TipoEdital).filter(TipoEdital.nome == nome).first()
        if not t:
            t = TipoEdital(nome=nome)
            db.add(t)
            db.flush()
        tipos_map[nome] = t

    # 3. Editais Iniciais
    exemplos = [
        {
            "identificador_origem": "deg-monitoria-01-2026",
            "titulo": "Edital Monitoria DEG 01/2026",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.",
            "url_pdf": "https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf",
            "data_publicacao": date(2026, 9, 1),
            "inicio_inscricao": date(2026, 9, 5),
            "fim_inscricao": date(2026, 12, 1),
            "campus": "Darcy Ribeiro",
            "tipo": "Monitoria",
        },
        {
            "identificador_origem": "deg-premio-inovacao-58-2026",
            "titulo": "Edital DEG N° 58/2026 – Prêmio Anual de Inovação no Ensino de Graduação da Universidade de Brasília",
            "resumo": "Incentivo a projetos inovadores no ensino de graduação da UnB.",
            "url_pdf": "https://deg.unb.br/edital-deg-n-58-2026-premio-anual-de-inovacao/",
            "data_publicacao": date(2026, 9, 23),
            "inicio_inscricao": date(2026, 9, 23),
            "fim_inscricao": date(2026, 11, 15),
            "campus": "Darcy Ribeiro",
            "tipo": "Extensões",
        },
        {
            "identificador_origem": "pibic-2026-2027",
            "titulo": "Edital PIBIC/PIBITI 2026/2027",
            "resumo": "Programa Institucional de Bolsas de Iniciação Científica e Tecnológica da UnB.",
            "url_pdf": "https://deg.unb.br/editais/edital-pibic-2026-2027.pdf",
            "data_publicacao": date(2026, 8, 15),
            "inicio_inscricao": date(2026, 8, 20),
            "fim_inscricao": date(2026, 10, 30),
            "campus": "Geral",
            "tipo": "PIBIC",
        },
    ]

    for item in exemplos:
        existente = db.query(Edital).filter(Edital.url_pdf == item["url_pdf"]).first()
        if not existente:
            novo = Edital(
                identificador_origem=item["identificador_origem"],
                titulo=item["titulo"],
                resumo=item["resumo"],
                url_pdf=item["url_pdf"],
                data_publicacao=item["data_publicacao"],
                inicio_inscricao=item["inicio_inscricao"],
                fim_inscricao=item["fim_inscricao"],
                status_processamento="processado",
            )
            novo.campi.append(campi_map[item["campus"]])
            novo.tipos.append(tipos_map[item["tipo"]])
            db.add(novo)

    db.commit()


def get_editais(
    db: Session,
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    campus: Optional[str] = None,
    busca: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Consulta editais no PostgreSQL aplicando filtros opcionais."""
    # Se a tabela estiver vazia, efetua o seed inicial
    if db.query(Edital).count() == 0:
        seed_initial_editais(db)

    query = db.query(Edital)
    today = date.today()

    if status == "aberto":
        query = query.filter(or_(Edital.fim_inscricao.is_(None), Edital.fim_inscricao >= today))
    elif status == "fechado":
        query = query.filter(Edital.fim_inscricao.is_not(None), Edital.fim_inscricao < today)

    if categoria:
        query = query.filter(Edital.tipos.any(TipoEdital.nome.ilike(f"%{categoria}%")))

    if campus:
        query = query.filter(Edital.campi.any(Campus.nome.ilike(f"%{campus}%")))

    if busca:
        busca_term = f"%{busca}%"
        query = query.filter(or_(Edital.titulo.ilike(busca_term), Edital.resumo.ilike(busca_term)))

    query = query.order_by(Edital.data_publicacao.desc().nullslast())
    editais = query.all()

    return [serialize_edital(e) for e in editais]


def get_edital_by_id(db: Session, edital_id: int) -> Optional[Dict[str, Any]]:
    """Busca um edital específico pelo ID no PostgreSQL."""
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        return None
    return serialize_edital(edital, detail=True)

