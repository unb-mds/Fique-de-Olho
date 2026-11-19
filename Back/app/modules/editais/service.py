"""Camada de serviço para operações de banco de dados do módulo de Editais."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from threading import Lock
import time
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy import and_, extract, or_
from sqlalchemy.orm import Session, defer, sessionmaker

from app.core.config import settings
from app.core.database import Campus, Edital, StatusEdital, TipoEdital

logger = logging.getLogger(__name__)


def _format_valor_bolsa_str(valor_bolsa: Any) -> Optional[str]:
    """Formata valor_bolsa (Decimal/float) como string monetária amigável ou ISO decimal."""
    if valor_bolsa is None:
        return None
    try:
        dec = Decimal(str(valor_bolsa))
        inteiro, centavos = f"{dec:.2f}".split(".")
        inteiro_fmt = f"{int(inteiro):,}".replace(",", ".")
        return f"R$ {inteiro_fmt},{centavos}"
    except Exception:
        return str(valor_bolsa)


def _infer_categoria(edital: Edital) -> str:
    """Classifica uma oportunidade a partir do texto disponível no registro."""
    partes = [
        edital.titulo or "",
        edital.resumo or "",
        edital.assunto or "",
        edital.tipo or "",
        " ".join(tipo.nome for tipo in (edital.tipos or [])),
    ]
    texto = _normalizar_texto_busca(" ".join(partes))

    regras = (
        ("Pós-graduação", ("pos-graduacao", "mestrado", "doutorado", "stricto sensu", "decanato de pos")),
        ("Intercâmbio", ("intercambio", "mobilidade", "exchange", "estudante internacional")),
        ("Evento", ("evento", "palestra", "seminario", "workshop", "congresso", "festival", "simpósio", "simposio")),
        ("Bolsa", ("bolsa", "bolsista", "auxilio", "auxílio", "pibic", "pibiti", "pibex")),
        ("Graduação", ("graduacao", "graduação", "licenciatura", "monitoria")),
        ("Pesquisa", ("pesquisa", "cientifica", "científica", "proic")),
        ("Estágio", ("estagio", "estágio")),
        ("Extensão", ("extensao", "extensão")),
        ("Vestibular", ("vestibular", "processo seletivo", "concurso")),
    )
    for categoria, termos in regras:
        if any(_normalizar_texto_busca(termo) in texto for termo in termos):
            return categoria

    tipo_nome = edital.tipo or ((edital.tipos or [None])[0].nome if edital.tipos else None)
    return tipo_nome or "Geral"


def _normalizar_texto_busca(valor: str) -> str:
    import unicodedata

    normalizado = unicodedata.normalize("NFD", valor)
    return "".join(char for char in normalizado if unicodedata.category(char) != "Mn").lower()


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
    tipo_nome = _infer_categoria(edital)

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
    valor_bolsa_num = (
        float(edital.valor_bolsa)
        if edital.valor_bolsa is not None
        else None
    )

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
        "orgao_emissor": edital.orgao_emissor,
        "orgaoEmissor": edital.orgao_emissor,
        "assunto": edital.assunto,
        "url_pagina": edital.url_pagina,
        "url_pdf": url_doc,
        "urlDocumento": url_doc,
        "data_publicacao": data_pub_val,
        "dataPublicacao": dt_pub_iso,
        "inicio_inscricao": inicio_insc_val,
        "fim_inscricao": fim_insc_val,
        "prazoFinal": dt_fim_iso,
        "status_processamento": edital.status_processamento or "processado",
        "vagas": edital.vagas,
        "valor_bolsa": valor_bolsa_num,
        "valor": _format_valor_bolsa_str(edital.valor_bolsa),
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
    today = date.today()
    exemplos = [
        {
            "identificador_origem": "deg-monitoria-01-2026",
            "titulo": "Edital Monitoria DEG 01/2026",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.",
            "url_pdf": "https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf",
            "data_publicacao": date(2026, 9, 1),
            "inicio_inscricao": date(2026, 9, 5),
            "fim_inscricao": today - timedelta(days=10),
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
            "fim_inscricao": today + timedelta(days=15),
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
            "fim_inscricao": today + timedelta(days=45),
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
    query = db.query(Edital).options(defer(Edital.texto_extraido))
    today = date.today()

    termo_busca = busca or q
    if termo_busca and termo_busca.strip():
        search_pattern = f"%{termo_busca.strip()}%"
        query = query.filter(
            or_(
                Edital.titulo.ilike(search_pattern),
                Edital.resumo.ilike(search_pattern),
                Edital.assunto.ilike(search_pattern),
                Edital.orgao_emissor.ilike(search_pattern),
            )
        )

    if ano is not None:
        query = query.filter(extract("year", Edital.data_publicacao) == ano)

    status_norm = status.strip().lower() if status and status.strip() else None
    if status_norm == "aberto":
        query = query.filter(
            or_(
                Edital.fim_inscricao >= today,
                and_(
                    Edital.fim_inscricao.is_(None),
                    or_(Edital.status.is_(None), Edital.status == StatusEdital.ABERTO),
                ),
            )
        )
    elif status_norm == "fechado":
        query = query.filter(
            or_(
                Edital.fim_inscricao < today,
                and_(
                    Edital.fim_inscricao.is_(None),
                    Edital.status == StatusEdital.ENCERRADO,
                ),
            )
        )

    if categoria and categoria.strip():
        categoria_normalizada = _normalizar_texto_busca(categoria)
        alias_categoria: Dict[str, tuple[str, ...]] = {
            "pos-graduacao": ("pós-graduação", "pos-graduacao", "mestrado", "doutorado", "stricto sensu", "ppg"),
            "graduacao": ("graduação", "graduacao", "licenciatura", "monitoria"),
            "intercambio": ("intercâmbio", "intercambio", "mobilidade", "exchange"),
            "evento": ("evento", "palestra", "seminário", "seminario", "workshop", "congresso", "festival"),
            "bolsa": ("bolsa", "bolsista", "auxílio", "auxilio", "pibic", "pibiti", "pibex"),
            "pesquisa": ("pesquisa", "científica", "cientifica", "proic"),
            "estagio": ("estágio", "estagio"),
            "extensao": ("extensão", "extensao"),
            "vestibular": ("vestibular", "concurso"),
            "monitoria": ("monitoria", "monitor"),
        }
        termos = alias_categoria.get(categoria_normalizada, (categoria.strip(),))
        filtros_categoria = []
        for termo in termos:
            pattern = f"%{termo}%"
            filtros_categoria.extend([
                Edital.titulo.ilike(pattern),
                Edital.resumo.ilike(pattern),
                Edital.assunto.ilike(pattern),
                Edital.tipo.ilike(pattern),
                Edital.tipos.any(TipoEdital.nome.ilike(pattern)),
            ])
        if filtros_categoria:
            query = query.filter(or_(*filtros_categoria))

    if campus and campus.strip():
        campus_pattern = f"%{campus.strip()}%"
        query = query.filter(
            or_(
                Edital.campus.ilike(campus_pattern),
                Edital.campi.any(Campus.nome.ilike(campus_pattern)),
            )
        )

    ordered_query = query.order_by(Edital.data_publicacao.desc().nullslast()).offset(skip).limit(limit)
    resultados = ordered_query.all()

    # Se não houver resultados e a tabela estiver vazia no PostgreSQL, popula o seed inicial sem custo de count() nas chamadas comuns
    if not resultados and db.bind and db.bind.dialect.name == "postgresql":
        if db.query(Edital.id).limit(1).first() is None:
            seed_initial_editais(db)
            resultados = ordered_query.all()

    return resultados


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


EDITAIS_CACHE_TTL_SECONDS = settings.EDITAIS_CACHE_TTL_SECONDS


def _normalizar_filtro(valor: Optional[str]) -> Optional[str]:
    return valor.strip().lower() if valor and valor.strip() else None


@dataclass(frozen=True)
class _CacheKey:
    bind_url: str
    ano: Optional[int]
    termo_busca: Optional[str]
    status: Optional[str]
    categoria: Optional[str]
    campus: Optional[str]
    skip: int
    limit: int

    @property
    def tem_filtro(self) -> bool:
        return any(
            p is not None
            for p in (self.ano, self.termo_busca, self.status, self.categoria, self.campus)
        ) or self.skip > 0


@dataclass
class _CacheEntry:
    timestamp: float
    payload: List[Dict[str, Any]]
    refreshing: bool = False


_EDITAIS_CACHE: Dict[_CacheKey, _CacheEntry] = {}
_CACHE_LOCK = Lock()
_CACHE_GENERATION = 0
_ULTIMO_BIND_ID: Optional[int] = None


def invalidar_cache_editais() -> None:
    """Invalida o cache em memória de listagens de editais."""
    global _CACHE_GENERATION
    with _CACHE_LOCK:
        _CACHE_GENERATION += 1
        _EDITAIS_CACHE.clear()


def _salvar_entrada_cache(chave: _CacheKey, geracao: int, payload: List[Dict[str, Any]]) -> None:
    with _CACHE_LOCK:
        if _CACHE_GENERATION == geracao:
            _EDITAIS_CACHE[chave] = _CacheEntry(
                timestamp=time.monotonic(),
                payload=payload,
                refreshing=False,
            )


def _revalidar_cache_editais(chave: _CacheKey, bind: Any, geracao: int) -> None:
    """Atualiza o cache de editais em segundo plano sem bloquear a resposta ao usuário."""
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=bind)
    db = session_factory()
    try:
        editais_db = list_editais_com_filtros(
            db=db,
            ano=chave.ano,
            q=chave.termo_busca,
            busca=chave.termo_busca,
            status=chave.status,
            categoria=chave.categoria,
            campus=chave.campus,
            skip=chave.skip,
            limit=chave.limit,
        )
        serializados = [serialize_edital(e) for e in editais_db] if editais_db else []
        if serializados or chave.tem_filtro:
            _salvar_entrada_cache(chave, geracao, serializados)
        else:
            with _CACHE_LOCK:
                if _CACHE_GENERATION == geracao:
                    _EDITAIS_CACHE.pop(chave, None)
    except Exception:
        logger.exception("Falha ao revalidar cache de editais em segundo plano.")
        with _CACHE_LOCK:
            if chave in _EDITAIS_CACHE:
                _EDITAIS_CACHE[chave].refreshing = False
    finally:
        db.close()


def listar_editais_com_cache(
    db: Session,
    agendar_tarefa: Optional[Callable[..., Any]] = None,
    ano: Optional[int] = None,
    q: Optional[str] = None,
    busca: Optional[str] = None,
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    campus: Optional[str] = None,
    skip: int = 0,
    limit: int = 24,
) -> Optional[List[Dict[str, Any]]]:
    """Retorna editais serializados usando cache Stale-While-Revalidate (ou None se sem dados sem filtro)."""
    global _ULTIMO_BIND_ID
    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    bind_id = id(bind) if bind is not None else 0

    with _CACHE_LOCK:
        if _ULTIMO_BIND_ID != bind_id:
            _ULTIMO_BIND_ID = bind_id
            _EDITAIS_CACHE.clear()

    chave_cache = _CacheKey(
        bind_url=str(getattr(bind, "url", "")) if bind is not None else "",
        ano=ano,
        termo_busca=_normalizar_filtro(busca or q),
        status=_normalizar_filtro(status),
        categoria=_normalizar_filtro(categoria),
        campus=_normalizar_filtro(campus),
        skip=skip,
        limit=limit,
    )
    agora = time.monotonic()

    with _CACHE_LOCK:
        entrada = _EDITAIS_CACHE.get(chave_cache)
        geracao_atual = _CACHE_GENERATION
        if entrada is not None:
            if agora - entrada.timestamp >= EDITAIS_CACHE_TTL_SECONDS and not entrada.refreshing:
                entrada.refreshing = True
                if bind is not None and agendar_tarefa is not None:
                    agendar_tarefa(_revalidar_cache_editais, chave_cache, bind, geracao_atual)
            return entrada.payload

    editais_db = list_editais_com_filtros(
        db=db,
        ano=chave_cache.ano,
        q=chave_cache.termo_busca,
        busca=chave_cache.termo_busca,
        status=chave_cache.status,
        categoria=chave_cache.categoria,
        campus=chave_cache.campus,
        skip=chave_cache.skip,
        limit=chave_cache.limit,
    )
    if editais_db:
        serializados = [serialize_edital(e) for e in editais_db]
        _salvar_entrada_cache(chave_cache, geracao_atual, serializados)
        return serializados

    if chave_cache.tem_filtro:
        _salvar_entrada_cache(chave_cache, geracao_atual, [])
        return []

    return None
