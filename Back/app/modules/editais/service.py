"""Camada de serviço para operações de banco de dados do módulo de Editais."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import and_, extract, or_
from sqlalchemy.orm import Session

from app.core.database import Campus, Edital, StatusEdital, TipoEdital


def serialize_edital(edital: Edital, detail: bool = False) -> Dict[str, Any]:
    """Serializa uma entidade Edital para formato compatível com o schema e o frontend."""
    today = date.today()

    if edital.fim_inscricao:
        fim_d = edital.fim_inscricao.date() if isinstance(edital.fim_inscricao, datetime) else edital.fim_inscricao
        status_edital = "aberto" if fim_d >= today else "fechado"
    elif edital.status:
        status_edital = edital.status.value if hasattr(edital.status, "value") else str(edital.status)
    else:
        status_edital = "aberto"

    campi_list = getattr(edital, "campi", []) or []
    tipos_list = getattr(edital, "tipos", []) or []
    docs_list = getattr(edital, "documentos", []) or []

    campus_nome = edital.campus or (campi_list[0].nome if campi_list else "Geral")
    tipo_nome = edital.tipo or (tipos_list[0].nome if tipos_list else "Geral")

    data_pub = edital.data_publicacao
    if isinstance(data_pub, datetime):
        data_pub_val = data_pub.date()
        dt_pub_iso = data_pub.isoformat()
    elif isinstance(data_pub, date):
        data_pub_val = data_pub
        dt_pub_iso = data_pub.isoformat()
    else:
        data_pub_val = None
        dt_pub_iso = None

    fim_insc = edital.fim_inscricao
    if isinstance(fim_insc, datetime):
        dt_fim_iso = fim_insc.isoformat()
        fim_insc_val = fim_insc.date()
    elif isinstance(fim_insc, date):
        dt_fim_iso = fim_insc.isoformat()
        fim_insc_val = fim_insc
    else:
        dt_fim_iso = None
        fim_insc_val = None

    inicio_insc = edital.inicio_inscricao
    if isinstance(inicio_insc, datetime):
        inicio_insc_val = inicio_insc.date()
    elif isinstance(inicio_insc, date):
        inicio_insc_val = inicio_insc
    else:
        inicio_insc_val = None

    url_doc = edital.url_pdf or (docs_list[0].url_pdf if docs_list else "") or edital.url_pagina or ""
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
        "tipo": tipo_nome,
        "url_pagina": edital.url_pagina,
        "url_pdf": url_doc,
        "urlDocumento": url_doc,
        "data_publicacao": data_pub_val,
        "dataPublicacao": dt_pub_iso,
        "inicio_inscricao": inicio_insc_val,
        "fim_inscricao": fim_insc_val,
        "prazoFinal": dt_fim_iso,
        "status_processamento": edital.status_processamento or "processado",
        "vagas": None,
        "valor": None,
        "campi": [{"id": c.id, "nome": c.nome} for c in campi_list],
        "tipos": [{"id": t.id, "nome": t.nome} for t in tipos_list],
        "documentos": [
            {
                "id": doc.id,
                "url_pdf": doc.url_pdf,
                "tipo_documento": doc.tipo_documento.value if hasattr(doc.tipo_documento, "value") else str(doc.tipo_documento),
            }
            for doc in docs_list
        ],
    }

    if detail:
        data.update({
            "identificador_origem": edital.identificador_origem,
            "texto_extraido": edital.texto_extraido,
            "hash_conteudo": edital.hash_conteudo,
            "criado_em": edital.criado_em or edital.created_at,
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
                url_pagina=item["url_pdf"],
                data_publicacao=item["data_publicacao"],
                inicio_inscricao=item["inicio_inscricao"],
                fim_inscricao=item["fim_inscricao"],
                status_processamento="processado",
                status=StatusEdital.ABERTO,
            )
            novo.campi.append(campi_map[item["campus"]])
            novo.tipos.append(tipos_map[item["tipo"]])
            db.add(novo)

    db.commit()


def list_editais_com_filtros(
    db: Session,
    ano: Optional[int] = None,
    q: Optional[str] = None,
    busca: Optional[str] = None,
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    campus: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Edital]:
    """Constrói dinamicamente a consulta SQLAlchemy aplicando filtros por ano, busca e categorias."""
    # Se a tabela estiver vazia e for conexão real com postgresql, realiza seed inicial
    if db.bind and db.bind.dialect.name == "postgresql" and db.query(Edital).count() == 0:
        seed_initial_editais(db)

    query = db.query(Edital)
    today = date.today()

    termo_busca = busca or q
    if termo_busca and termo_busca.strip():
        search_pattern = f"%{termo_busca.strip()}%"
        query = query.filter(
            or_(
                Edital.titulo.ilike(search_pattern),
                Edital.resumo.ilike(search_pattern),
            )
        )

    if ano is not None:
        query = query.filter(extract("year", Edital.data_publicacao) == ano)

    if status == "aberto":
        query = query.filter(
            or_(
                Edital.status == StatusEdital.ABERTO,
                Edital.fim_inscricao.is_(None),
                Edital.fim_inscricao >= today,
            )
        )
    elif status == "fechado":
        query = query.filter(
            or_(
                Edital.status == StatusEdital.ENCERRADO,
                and_(Edital.fim_inscricao.is_not(None), Edital.fim_inscricao < today),
            )
        )

    if categoria and categoria.strip():
        cat_pattern = f"%{categoria.strip()}%"
        query = query.filter(
            or_(
                Edital.tipo.ilike(cat_pattern),
                Edital.tipos.any(TipoEdital.nome.ilike(cat_pattern)),
            )
        )

    if campus and campus.strip():
        campus_pattern = f"%{campus.strip()}%"
        query = query.filter(
            or_(
                Edital.campus.ilike(campus_pattern),
                Edital.campi.any(Campus.nome.ilike(campus_pattern)),
            )
        )

    return query.order_by(Edital.data_publicacao.desc().nullslast()).offset(skip).limit(limit).all()


def get_editais(
    db: Session,
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    campus: Optional[str] = None,
    busca: Optional[str] = None,
    ano: Optional[int] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Consulta editais no PostgreSQL aplicando filtros opcionais e retornando lista serializada."""
    editais = list_editais_com_filtros(
        db=db,
        ano=ano,
        q=q,
        busca=busca,
        status=status,
        categoria=categoria,
        campus=campus,
        skip=skip,
        limit=limit,
    )
    return [serialize_edital(e) for e in editais]


def get_edital_by_id(db: Session, edital_id: int) -> Optional[Edital]:
    """Busca um edital específico pelo ID no PostgreSQL."""
    return db.query(Edital).filter(Edital.id == edital_id).first()
