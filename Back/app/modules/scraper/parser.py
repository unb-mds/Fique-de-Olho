"""Módulo extensível de parsing e extração de metadados de editais da UnB.

Capaz de analisar o texto e tabelas extraídos de PDFs para identificar:
- Órgão emissor da UnB (DEG, DPG, DEX, DPI, DAC, INT, PROIC, DACES, BCE);
- Período de inscrição (data de início e término);
- Datas de resultado preliminar e final;
- Campus mencionado (Darcy Ribeiro, FGA, FCE, FUP);
- Vagas e indicação de bolsas remuneradas.

Também concentra a Camada 1 (heurística determinística, offline e de custo zero) das
Issues #77 e #106: extração do objeto do edital para resumo automático e detecção /
reconstrução de títulos vagos ou genéricos.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field

from app.modules.scraper.pdf import PDFDocumentExtraction

logger = logging.getLogger(__name__)

MESES_PT = {
    "janeiro": 1, "jan": 1,
    "fevereiro": 2, "fev": 2, "feb": 2,
    "marco": 3, "março": 3, "mar": 3,
    "abril": 4, "abr": 4, "apr": 4,
    "maio": 5, "mai": 5, "may": 5,
    "junho": 6, "jun": 6,
    "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8, "aug": 8,
    "setembro": 9, "set": 9, "sep": 9,
    "outubro": 10, "out": 10, "oct": 10,
    "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12, "dec": 12,
}

# Órgãos, Decanatos e Portais da UnB mapeados para extensibilidade multi-portal
ORGAOS_UNB: Dict[str, Tuple[str, ...]] = {
    "DEG": ("decanato de ensino de graduacao", "decanato de ensino de graduação", "deg"),
    "DPG": ("decanato de pos-graduacao", "decanato de pós-graduação", "dpg"),
    "DEX": ("decanato de extensao", "decanato de extensão", "dex"),
    "DPI": ("decanato de pesquisa e inovacao", "decanato de pesquisa e inovação", "dpi"),
    "DAC": ("decanato de assuntos comunitarios", "decanato de assuntos comunitários", "dac"),
    "INT": ("secretaria de assuntos internacionais", "assuntos internacionais", "int"),
    "PROIC": ("programa de iniciacao cientifica", "programa de iniciação científica", "proic"),
    "DACES": ("diretoria de acessibilidade", "daces"),
    "BCE": ("biblioteca central", "bce"),
    "CEAD": ("centro de educacao a distancia", "centro de educação a distância", "cead", "uab/unb"),
    "SIGAA": ("sistema integrado de gestao de atividades academicas", "sigaa"),
    "CEBRASPE": ("centro brasileiro de pesquisa em avaliacao e selecao", "cebraspe", "cespe"),
    "UNB_IDIOMAS": ("unb idiomas", "escola de linguas", "unbidiomas"),
    "CONCURSOS": ("concursos unb", "concursos.unb.br", "portal de concursos"),
    "DGP": ("decanato de gestao de pessoas", "decanato de gestão de pessoas", "dgp"),
    "FINATEC": (
        "fundacao de empreendimentos cientificos e tecnologicos",
        "fundação de empreendimentos científicos e tecnológicos",
        "finatec",
    ),
    "CDT": ("centro de apoio ao desenvolvimento tecnologico", "centro de apoio ao desenvolvimento tecnológico", "cdt"),
    "PCTEC": ("parque cientifico e tecnologico", "parque científico e tecnológico", "pctec"),
    "HUB": ("hospital universitario de brasilia", "hospital universitário de brasília", "hub-unb", "ebserh", "hub"),
    "FAL": ("fazenda agua limpa", "fazenda água limpa", "fal"),
    "OCEAN": ("samsung ocean", "ocean brasil", "ocean unb", "ocean"),
    "CEL": ("coordenacao de esporte e lazer", "coordenação de esporte e lazer", "diretoria de esporte", "cel"),
    "CAL": ("casa da cultura da america latina", "casa da cultura da américa latina", "cal"),
    "EDU": ("editora universidade de brasilia", "editora unb", "edu"),
    "UNBTV": ("unbtv", "unb tv", "televisao universitaria"),
    "FUP": ("faculdade unb planaltina", "faculdade de planaltina", "fup"),
    "FACE": (
        "faculdade de economia, administracao, contabilidade",
        "faculdade de economia, administração, contabilidade",
        "face",
    ),
    "DIREITO": ("faculdade de direito", "fd/unb", "direito unb"),
    "DAF": ("decanato de administracao", "decanato de administração", "daf"),
    "PRC": ("prefeitura do campus", "prefeitura da unb", "prc"),
    "DOU": ("diario oficial da uniao", "diário oficial da união", "imprensa nacional", "dou"),
    "PPGCONT": ("programa de pos-graduacao em ciencias contabeis", "ppgcont"),
    "PPGGIPP": ("gestao publica", "ppggipp", "ppgipp"),
}

# Campus da UnB
CAMPUS_UNB: Dict[str, Tuple[str, ...]] = {
    "Darcy Ribeiro": ("darcy ribeiro", "plano piloto", "campus darcy", "asa norte"),
    "FGA": ("faculdade do gama", "campus gama", "fga", "gama"),
    "FCE": ("faculdade de ceilandia", "faculdade da ceilândia", "campus ceilandia", "fce", "ceilandia", "ceilândia"),
    "FUP": ("faculdade de planaltina", "campus planaltina", "fup", "planaltina"),
}


class CronogramaEtapa(BaseModel):
    """Representa uma etapa individual encontrada no cronograma do edital."""

    etapa: str
    periodo_texto: str
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None


class EditalMetadados(BaseModel):
    """Contrato estruturado de saída com metadados extraídos do edital."""

    orgao_emissor: Optional[str] = None
    campus: Optional[str] = None
    inicio_inscricao: Optional[datetime] = None
    fim_inscricao: Optional[datetime] = None
    data_resultado_preliminar: Optional[datetime] = None
    data_resultado_final: Optional[datetime] = None
    vagas: Optional[int] = None
    bolsa_remunerada: Optional[bool] = None
    valor_bolsa: Optional[float] = None
    cronograma: List[CronogramaEtapa] = Field(default_factory=list)


def _strip_accents(text: str) -> str:
    """Remove acentos e converte para minúsculas para buscas fonéticas/lexicais."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()


def parse_date_pt(day_str: str, month_str: str, year_str: str) -> Optional[datetime]:
    """Converte dia, mês (nome ou número) e ano para datetime UTC com validação."""
    try:
        day = int(day_str)
        cleaned_month = _strip_accents(month_str.strip())
        if cleaned_month.isdigit():
            month = int(cleaned_month)
        else:
            month = MESES_PT.get(cleaned_month, 1)

        year = int(year_str)
        if year < 100:
            year += 2000

        return datetime(year, month, day, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def parse_data_interval(text: str, default_year: Optional[int] = None) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Extrai data de início e término a partir de uma expressão textual de intervalo.

    Formatos suportados:
    - '23 de setembro a 14 de outubro de 2026'
    - '23 a 30 de setembro de 2026'
    - '15/09/2026 a 30/09/2026' ou '15/09 a 30/09/2026'
    - '02 a 06/03/2026' (dia1 a dia2/mes/ano)
    - '05 a 12 de mar de 2026' (meses abreviados)
    - 'até às 18h do dia 15 de dezembro de 2026' (limite extenso)
    - 'inscrições até 23:59 do dia 20/11/2026' (limite numérico)
    - '14 de outubro de 2026' (data única -> início e fim iguais)
    - '14/10/2026'
    """
    if not text or not text.strip():
        return None, None

    clean = text.strip()

    # 0a. Limite por extenso: 'até às 18h do dia 15 de dezembro de 2026'
    p_lim_ext = re.search(
        r"at[eé]\s+(?:[aà]s\s+)?(?:\d{1,2}[:h]\d{0,2})?\s*(?:h(?:oras)?)?\s*(?:do\s+dia\s+)?(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})",
        clean,
        re.I,
    )
    if p_lim_ext:
        d, m, y = p_lim_ext.groups()
        dt_fim = parse_date_pt(d, m, y)
        return None, dt_fim

    # 0b. Limite numérico: 'inscrições até 23:59 do dia 20/11/2026'
    p_lim_num = re.search(
        r"at[eé]\s+(?:[aà]s\s+)?(?:\d{1,2}[:h]\d{0,2})?\s*(?:h(?:oras)?)?\s*(?:do\s+dia\s+)?(\d{1,2})/(\d{1,2})/(\d{2,4})",
        clean,
        re.I,
    )
    if p_lim_num:
        d, m, y = p_lim_num.groups()
        dt_fim = parse_date_pt(d, m, y)
        return None, dt_fim

    # 0c. '01/04/2026 a 15/04/2026' (duas datas completas)
    p_slash_full = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{2,4})\s+(?:a|ate|até)\s+(\d{1,2})/(\d{1,2})/(\d{2,4})",
        clean,
        re.I,
    )
    if p_slash_full:
        d1, m1, y1, d2, m2, y2 = p_slash_full.groups()
        return parse_date_pt(d1, m1, y1), parse_date_pt(d2, m2, y2)

    # 0d. '02 a 06/03/2026' (dia1 a dia2/mes/ano)
    p_slash_compact = re.search(
        r"(\d{1,2})\s+(?:a|ate|até)\s+(\d{1,2})/(\d{1,2})/(\d{2,4})",
        clean,
        re.I,
    )
    if p_slash_compact:
        d1, d2, m, y = p_slash_compact.groups()
        return parse_date_pt(d1, m, y), parse_date_pt(d2, m, y)

    # 1. '23 de setembro a 14 de outubro de 2026'
    p1 = re.search(
        r"(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)(?:\s+de\s+(\d{4}))?\s+(?:a|ate|até)\s+(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})",
        clean,
        re.I,
    )
    if p1:
        d1, m1, y1_opt, d2, m2, y2 = p1.groups()
        y1 = y1_opt or y2
        dt_ini = parse_date_pt(d1, m1, y1)
        dt_fim = parse_date_pt(d2, m2, y2)
        return dt_ini, dt_fim

    # 2. '23 a 30 de setembro de 2026' ou '05 a 12 de mar de 2026' (mesmo mês)
    p2 = re.search(
        r"(\d{1,2})\s+(?:a|ate|até)\s+(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})",
        clean,
        re.I,
    )
    if p2:
        d1, d2, m, y = p2.groups()
        return parse_date_pt(d1, m, y), parse_date_pt(d2, m, y)

    # 3. '15/09/2026 a 30/09/2026' ou '15/09 a 30/09/2026'
    p3 = re.search(
        r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s+(?:a|ate|até)\s+(\d{1,2})/(\d{1,2})/(\d{2,4})",
        clean,
        re.I,
    )
    if p3:
        d1, m1, y1_opt, d2, m2, y2 = p3.groups()
        y1 = y1_opt or y2
        return parse_date_pt(d1, m1, y1), parse_date_pt(d2, m2, y2)

    # 4. Data única por extenso: '14 de outubro de 2026'
    p4 = re.search(
        r"(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})",
        clean,
        re.I,
    )
    if p4:
        d, m, y = p4.groups()
        single = parse_date_pt(d, m, y)
        return single, single

    # 5. Data única numérica: '14/10/2026'
    p5 = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{2,4})",
        clean,
        re.I,
    )
    if p5:
        d, m, y = p5.groups()
        single = parse_date_pt(d, m, y)
        return single, single

    # 6. '23 a 30 de setembro' com ano default
    if default_year:
        p6 = re.search(
            r"(\d{1,2})\s+(?:a|ate|até)\s+(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)",
            clean,
            re.I,
        )
        if p6:
            d1, d2, m = p6.groups()
            return parse_date_pt(d1, m, str(default_year)), parse_date_pt(d2, m, str(default_year))

    return None, None


def detect_orgao_emissor(text: str) -> Optional[str]:
    """Identifica o órgão/decanato emissor a partir do texto do edital."""
    if not text or not text.strip():
        return None
    clean = _strip_accents(text)

    # Prioriza cabeçalho das primeiras 2000 letras onde o emissor normalmente se declara
    header = clean[:2500]

    for orgao, termos in ORGAOS_UNB.items():
        for termo in termos:
            termo_clean = _strip_accents(termo)
            # Termos curtos como 'deg' usam fronteira de palavra
            if len(termo_clean) <= 5:
                if re.search(rf"\b{re.escape(termo_clean)}\b", header):
                    return orgao
            elif termo_clean in header:
                return orgao

    # Se não achou no cabeçalho, procura no documento inteiro
    for orgao, termos in ORGAOS_UNB.items():
        for termo in termos:
            termo_clean = _strip_accents(termo)
            if len(termo_clean) <= 5:
                if re.search(rf"\b{re.escape(termo_clean)}\b", clean):
                    return orgao
            elif termo_clean in clean:
                return orgao

    return None


def extrair_orgao_emissor(text: str) -> Optional[str]:
    """Alias compatível com a especificação para detecção do órgão emissor."""
    return detect_orgao_emissor(text)


def detect_campus(text: str) -> Optional[str]:
    """Identifica o campus da UnB mencionado com maior relevância no texto."""
    clean = _strip_accents(text)

    for campus, termos in CAMPUS_UNB.items():
        for termo in termos:
            if re.search(rf"\b{re.escape(termo)}\b", clean):
                return campus

    # Se menciona 'Universidade de Brasília' genérico sem campus específico
    if "universidade de brasilia" in clean:
        return "Geral"

    return None


def detect_vagas(text: str) -> Optional[int]:
    """Identifica quantidade de vagas ofertadas no edital."""
    patterns = [
        r"(\d+)\s+(?:vagas|vaga|bolsas|bolsa)\b",
        r"(?:vagas|bolsas):\s*(\d+)\b",
        r"total de\s+(\d+)\s+vagas\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try:
                qtd = int(m.group(1))
                if 0 < qtd < 10000:
                    return qtd
            except ValueError:
                continue
    return None


def detect_bolsa(text: str) -> Tuple[Optional[bool], Optional[float]]:
    """Identifica se há oferta de bolsa remunerada e seu valor monetário.

    Filtra taxas de inscrição, multas e orçamentos globais de projetos por contexto
    e teto de valor (R$ 15.000,00). Detecta também menções qualitativas a bolsas
    (PIBIC, auxílio financeiro) ou declarações de trabalho voluntário/sem remuneração.
    """
    clean = text.lower()
    valor_bolsa: Optional[float] = None
    tem_bolsa: Optional[bool] = None

    termos_desqualificadores = (
        "taxa", "inscricao", "inscrição", "inscricoes", "inscrições",
        "gru", "recolhimento", "orcamento", "orçamento", "custo", "multa",
        "total do projeto", "orcamento global", "orçamento global",
    )
    termos_qualificadores = (
        "bolsa", "bolsista", "auxilio", "auxílio", "remuneracao", "remuneração",
        "mensal", "mensais", "retribuicao", "retribuição", "estipendio", "estipêndio",
        "beneficio", "benefício", "valor mensal", "concessao de bolsa", "concessão de bolsa",
    )

    candidatos_validos: List[Tuple[float, bool]] = []
    for m in re.finditer(r"r\$\s*([\d\.]+,\d{2})", clean):
        raw_val = m.group(1).replace(".", "").replace(",", ".")
        try:
            val = float(raw_val)
        except ValueError:
            continue

        if val > 15000.0 or val <= 0:
            continue

        start_ctx = max(
            clean.rfind("\n", 0, m.start()),
            clean.rfind(".", 0, m.start()),
            clean.rfind(";", 0, m.start()),
        )
        end_ctx = len(clean)
        for separator in ("\n", ".", ";"):
            pos = clean.find(separator, m.end())
            if pos != -1:
                end_ctx = min(end_ctx, pos)
        contexto = clean[max(0, start_ctx):end_ctx]

        tem_desqualificador = any(td in contexto for td in termos_desqualificadores)
        tem_qualificador = any(tq in contexto for tq in termos_qualificadores)

        if tem_qualificador and not tem_desqualificador:
            candidatos_validos.append((val, True))
        elif not tem_desqualificador:
            candidatos_validos.append((val, False))

    if candidatos_validos:
        qualificados = [c for c in candidatos_validos if c[1]]
        if qualificados:
            valor_bolsa = qualificados[0][0]
            tem_bolsa = True

    if tem_bolsa is None:
        termos_sem_remuneracao = (
            "voluntário", "voluntario", "sem remuneração", "sem remuneracao",
            "nao remunerado", "não remunerado", "sem bolsa", "sem ônus", "sem onus",
        )
        termos_com_bolsa = (
            "bolsa remunerada", "bolsista remunerado", "auxílio financeiro", "auxilio financeiro",
            "bolsa de pesquisa", "bolsa de extensao", "bolsa de extensão", "bolsa de monitoria",
            "bolsa de iniciacao", "bolsa de iniciação", "concessao de bolsa", "concessão de bolsa",
            "pibic", "pibiti", "pibex", "auxilio permanencia", "auxílio permanência",
        )
        if any(w in clean for w in termos_sem_remuneracao):
            tem_bolsa = False
        elif any(w in clean for w in termos_com_bolsa):
            tem_bolsa = True

    return tem_bolsa, valor_bolsa


def _add_business_days(start_date: datetime, n_days: int) -> datetime:
    """Soma N dias úteis (segunda a sexta) a uma data inicial."""
    current = start_date
    added = 0
    while added < n_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def parse_cronograma_from_tables(tables: List[List[List[Optional[str]]]]) -> List[CronogramaEtapa]:
    """Varre tabelas extraídas em busca de estruturas de cronograma e etapas."""
    etapas_encontradas: List[CronogramaEtapa] = []

    for table in tables:
        if not table or len(table) < 2:
            continue

        header = " ".join(str(cell or "").lower() for cell in table[0])
        eh_tabela_cronograma = any(
            k in header for k in ["etapa", "fase", "atividade", "cronograma", "evento"]
        ) and any(
            k in header for k in ["data", "periodo", "período", "prazo"]
        )

        if not eh_tabela_cronograma:
            continue

        for row in table[1:]:
            if len(row) < 2 or not row[0] or not row[1]:
                continue

            nome_etapa = str(row[0]).strip().replace("\n", " ")
            periodo_str = str(row[1]).strip().replace("\n", " ")

            if not nome_etapa or not periodo_str:
                continue

            dt_ini, dt_fim = parse_data_interval(periodo_str)

            etapas_encontradas.append(
                CronogramaEtapa(
                    etapa=nome_etapa,
                    periodo_texto=periodo_str,
                    inicio=dt_ini,
                    fim=dt_fim,
                )
            )

    return etapas_encontradas


def parse_edital_metadados(
    doc: Union[PDFDocumentExtraction, str],
    ano_referencia: Optional[int] = None,
    data_publicacao: Optional[datetime] = None,
) -> EditalMetadados:
    """Extrai metadados completos de um documento de edital.

    Args:
        doc: Objeto PDFDocumentExtraction (contendo texto e tabelas) ou string de texto simples.
        ano_referencia: Ano do edital para desambiguação de datas quando não explícito no texto.
        data_publicacao: Data de publicação do edital para cálculo de prazos relativos.

    Returns:
        EditalMetadados: Modelo preenchido com todos os campos identificados com segurança.
    """
    if isinstance(doc, PDFDocumentExtraction):
        full_text = doc.full_text
        tables = doc.tables
    else:
        full_text = str(doc)
        tables = []

    # 1. Órgão e Campus
    orgao = detect_orgao_emissor(full_text)
    campus = detect_campus(full_text)

    # 2. Vagas e Bolsas
    vagas = detect_vagas(full_text)
    bolsa_rem, valor_bolsa = detect_bolsa(full_text)

    # 3. Cronograma via tabelas
    cronograma = parse_cronograma_from_tables(tables)

    inicio_inscricao: Optional[datetime] = None
    fim_inscricao: Optional[datetime] = None
    dt_res_preliminar: Optional[datetime] = None
    dt_res_final: Optional[datetime] = None

    for item in cronograma:
        etapa_clean = _strip_accents(item.etapa)

        if "inscric" in etapa_clean:
            if not inicio_inscricao and item.inicio:
                inicio_inscricao = item.inicio
            if item.fim:
                fim_inscricao = item.fim
            elif item.inicio and not fim_inscricao:
                fim_inscricao = item.inicio

        elif any(k in etapa_clean for k in ["resultado preliminar", "resultado parcial", "homologacao das inscricoes", "homologação"]):
            if not dt_res_preliminar:
                dt_res_preliminar = item.fim or item.inicio

        elif any(k in etapa_clean for k in ["resultado final", "divulgacao do resultado final", "divulgação do resultado final"]):
            if not dt_res_final:
                dt_res_final = item.fim or item.inicio

    # 4. Fallback no corpo do texto para inscrições se a tabela não trouxe datas
    if not (inicio_inscricao and fim_inscricao):
        # Procura seção de inscrições no texto
        m_secao = re.search(
            r"(?:das\s+inscri[cç][oõ]es|per[ií]odo\s+de\s+inscri[cç][aã]o|inscri[cç][oõ]es)[^\.\n]{0,80}?[:\-]?\s*([^\.\n]+)",
            full_text,
            re.I,
        )
        trecho = m_secao.group(1) if m_secao else full_text
        dt_ini_txt, dt_fim_txt = parse_data_interval(trecho, default_year=ano_referencia)

        if not inicio_inscricao:
            inicio_inscricao = dt_ini_txt
        if not fim_inscricao:
            fim_inscricao = dt_fim_txt or dt_ini_txt

    # 5. Cálculo de prazo relativo (dias úteis ou corridos) a partir da data de publicação
    if not fim_inscricao and data_publicacao:
        m_dias_uteis = re.search(
            r"(\d+)\s+dias\s+[uú]teis\s+(?:a\s+contar|contados|a\s+partir|ap[oó]s)",
            full_text,
            re.I,
        )
        if m_dias_uteis:
            qtd_dias = int(m_dias_uteis.group(1))
            fim_inscricao = _add_business_days(data_publicacao, qtd_dias)
            if not inicio_inscricao:
                inicio_inscricao = data_publicacao
        else:
            m_dias_corridos = re.search(
                r"(\d+)\s+dias\s+corridos\s+(?:a\s+contar|contados|a\s+partir|ap[oó]s)",
                full_text,
                re.I,
            )
            if m_dias_corridos:
                qtd_dias = int(m_dias_corridos.group(1))
                fim_inscricao = data_publicacao + timedelta(days=qtd_dias)
                if not inicio_inscricao:
                    inicio_inscricao = data_publicacao

    return EditalMetadados(
        orgao_emissor=orgao,
        campus=campus,
        inicio_inscricao=inicio_inscricao,
        fim_inscricao=fim_inscricao,
        data_resultado_preliminar=dt_res_preliminar,
        data_resultado_final=dt_res_final,
        vagas=vagas,
        bolsa_remunerada=bolsa_rem,
        valor_bolsa=valor_bolsa,
        cronograma=cronograma,
    )



# ============================================================================
# Camada 1 — Heurística determinística local (Issues #77 e #106)
# Offline, custo zero e usada como fallback da Camada 2 (LLM).
# ============================================================================

MAX_RESUMO_CHARS = 350
MAX_TITULO_CHARS = 140
_MAX_ASSUNTO_TITULO_CHARS = 80
_MAX_SUBJECT_CHARS = 70
_CABECALHO_JANELA_CHARS = 1500

# Linhas de ruído típicas de PDFs gerados pelo SEI, Boletim de Atos e DOU.
_NOISE_LINE_RE = re.compile(
    "|".join(
        (
            r"^\s*SEI\s*/\s*\w+\s*-\s*\d+.*$",  # SEI/UnB - 11223344 - Edital
            r"^\s*SEI\s+n[º°o.]?\s*\d+.*$",
            r"^\s*Refer[eê]ncia:\s*Processo.*$",
            r"^.*Documento assinado eletronicamente.*$",
            r"^.*autenticidade (?:deste|do) documento.*$",
            r"^.*controlador_externo\.php.*$",
            r"^\s*Criado por .*$",
            r"^\s*P[áa]g(?:ina|\.)?\s*\d+\s*(?:de|/)\s*\d+\s*$",
            r"^\s*\d{1,3}\s*(?:de|/)\s*\d{1,3}\s*$",
            r"^\s*\d{1,3}\s*$",
            r"^.*Boletim de Atos Oficiais.*$",
            r"^.*Di[áa]rio Oficial da Uni[ãa]o.*$",
            r"^.*Imprensa Nacional.*$",
            r"^\s*Publicado em:.*$",
            r"^\s*Edi[çc][ãa]o:.*$",
            r"^\s*https?://\S+\s*$",
        )
    ),
    re.IGNORECASE | re.MULTILINE,
)

_ENUM = r"(?:\d{1,2}(?:\.\d{1,2})*\.?|[IVXL]{1,5})"
_SEP = r"[\.\-–—)]"

# Seções padronizadas em ordem de prioridade para compor o resumo (Issue #77).
_SECOES_OBJETO: Tuple[str, ...] = (
    r"OBJETO",
    r"OBJETIVOS?",
    r"FINALIDADE",
    r"PROGRAMA",
    r"DISPOSI[ÇC][ÕO]ES\s+PRELIMINARES",
    r"APRESENTA[ÇC][ÃA]O",
)

_PROXIMA_SECAO_RE = re.compile(
    rf"^[ \t]*(?:(?:\d{{1,2}}|[IVXL]{{1,5}})\s*{_SEP}\s*)?(?:D[OA]S?|ANEXO|CAP[ÍI]TULO)\b[A-ZÀ-Ý0-9 \t,/\-–]*$"
    rf"|^[ \t]*(?:\d{{1,2}}|[IVXL]{{1,5}})\s*{_SEP}\s*[A-ZÀ-Ý][A-ZÀ-Ý \t,/\-–]{{3,}}$",
    re.MULTILINE,
)

_SUBITEM_RE = re.compile(r"^[ \t]*\d{1,2}(?:\.\d{1,2})+\.?[ \t]+", re.MULTILINE)

# Resto de título de seção em caixa alta grudado no corpo (", HABILITAÇÃO E AVALIAÇÃO Para ...").
_CAIXA_ALTA_INICIAL_RE = re.compile(
    r"^[\s,;:\-–]*(?:(?:[A-ZÀ-Ý]{2,}|E|À)[\s,;:/\-–]+)+(?=[A-ZÀ-Ý][a-zà-ÿ])"
)

_TORNA_PUBLICO_RE = re.compile(
    r"torna(?:m)?\s+p[úu]blic[oa]s?\s+(?:a|o|as|os)?\s*(.+?)(?:\.\s|\.$|$)",
    re.IGNORECASE,
)

# "presente instrumento/regulamento/edital para ..." → mantém só o que interessa ao estudante.
_PRESENTE_INSTRUMENTO_RE = re.compile(
    r"^(?:(?:o|a)\s+)?presentes?\s+(?:instrumento|regulamento|edital|chamada|chamamento|processo)"
    r"(?:\s+(?:para|que\s+(?:trata|disp[õo]e)\s+(?:sobre|d[aoe]s?)|de|com\s+vistas\s+[àa]))?\s+(?:(?:a|o|à)\s+)?",
    re.IGNORECASE,
)
_BOILERPLATE_FINAL_RE = re.compile(
    r",?\s+(?:de\s+acordo\s+com|conforme\s+(?:os\s+termos|as\s+condi)|nos\s+termos\s+d)",
    re.IGNORECASE,
)

_CABECALHO_RE = re.compile(
    r"^[ \t]*((?:EDITAL|CHAMADA|CHAMAMENTO|AVISO|PORTARIA|RESOLU[ÇC][ÃA]O)\b[^\n]{0,200})$",
    re.IGNORECASE | re.MULTILINE,
)

_NUMERO_EDITAL_RE = re.compile(r"\d+\s*/\s*\d{2,4}")

# Títulos genéricos / etapas isoladas (comparação sem acentos e sem caixa) — Issue #106.
_TITULOS_GENERICOS_RAW: Tuple[str, ...] = (
    "edital", "edital de abertura", "edital complementar", "edital sem titulo", "edital completo",
    "chamada publica", "aviso", "comunicado", "retificacao", "resultado", "resultado preliminar",
    "resultado provisorio", "resultado final", "homologacao", "convocacao", "convocacoes",
    "convocacao para entrevista", "nomeacao", "nomeacoes", "lista de inscritos", "listas de inscritos",
    "selecao de tutores a distancia", "selecao de tutores presenciais", "processo de selecao simplificada",
    "processo seletivo", "normas e orientacoes", "clique aqui", "acesse aqui", "download", "arquivo",
    "documento", "resultado provisorio: aqui", "inscricoes abertas", "aqui", "saiba mais", "leia mais",
    "veja mais", "mais informacoes", "anexo", "anexos",
)

_STAGE_PREFIXES: Tuple[str, ...] = (
    "convocacao", "convocacoes", "resultado preliminar", "resultado provisorio", "resultado parcial",
    "resultado final", "retificacao", "homologacao", "nomeacao", "nomeacoes",
)

# Termos que caracterizam programa/curso/área e tornam um título de etapa específico.
_TERMOS_ESPECIFICOS: Tuple[str, ...] = (
    "monitoria", "mestrado", "doutorado", "especializacao", "residencia", "graduacao", "pos graduacao",
    "extensao", "pesquisa", "iniciacao", "bolsa", "bolsas", "auxilio", "estagio", "vestibular",
    "transferencia", "concurso", "curso", "disciplina", "projeto", "intercambio", "mobilidade",
    "moradia", "alimentacao", "premio", "idiomas", "pibic", "pibiti", "pibex", "pibid", "proic",
    "capes", "cnpq", "fapdf", "uab", "enem", "sisu", "tutoria", "tutores",
)

# Rótulos de etapa/ato úteis preservados ao reconstruir títulos vagos.
_ROTULOS_UTEIS: Tuple[Tuple[str, str], ...] = (
    ("processo de selecao simplificada", "Processo de Seleção Simplificada"),
    ("selecao de tutores a distancia", "Seleção de Tutores a Distância"),
    ("selecao de tutores presenciais", "Seleção de Tutores Presenciais"),
    ("convocacao para entrevista", "Convocação para Entrevista"),
    ("convocacao para matricula", "Convocação para Matrícula"),
    ("resultado preliminar", "Resultado Preliminar"),
    ("resultado provisorio", "Resultado Provisório"),
    ("resultado parcial", "Resultado Parcial"),
    ("resultado final", "Resultado Final"),
    ("listas de inscritos", "Lista de Inscritos"),
    ("lista de inscritos", "Lista de Inscritos"),
    ("edital complementar", "Edital Complementar"),
    ("normas e orientacoes", "Normas e Orientações"),
    ("inscricoes abertas", "Inscrições Abertas"),
    ("processo seletivo", "Processo Seletivo"),
    ("chamada publica", "Chamada Pública"),
    ("convocacoes", "Convocações"),
    ("convocacao", "Convocação"),
    ("nomeacoes", "Nomeações"),
    ("nomeacao", "Nomeação"),
    ("retificacao", "Retificação"),
    ("homologacao", "Homologação"),
    ("comunicado", "Comunicado"),
    ("resultado", "Resultado"),
    ("aviso", "Aviso"),
)

# Siglas com grafia oficial preservada no Title Case.
_SIGLAS_EXTRA: Dict[str, str] = {
    "UNB": "UnB", "CNPQ": "CNPq", "Nº": "Nº", "N°": "Nº",
    "PIBIC": "PIBIC", "PIBITI": "PIBITI", "PIBIC-AF": "PIBIC-AF", "PIBIC-EM": "PIBIC-EM",
    "PIBEX": "PIBEX", "PIBID": "PIBID", "FAPDF": "FAPDF", "UAB": "UAB", "MEI": "MEI", "PGD": "PGD",
    "CAPES": "CAPES", "EBSERH": "EBSERH", "FGA": "FGA", "FCE": "FCE", "EAD": "EaD", "TCC": "TCC",
    "PET": "PET", "ENEM": "ENEM", "SISU": "SiSU", "PAS": "PAS", "DF": "DF", "IA": "IA", "PPG": "PPG",
}
SIGLAS_PRESERVADAS: Dict[str, str] = {
    **{k: k for k in ORGAOS_UNB if "_" not in k},
    **_SIGLAS_EXTRA,
}
_PROGRAMAS_ROTULO = {"PIBIC", "PIBITI", "PIBIC-AF", "PIBIC-EM", "PIBEX", "PIBID", "PROIC", "PET", "MEI", "PGD"}

_MINUSCULAS_PT = {
    "a", "o", "as", "os", "e", "ou", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "por", "pelo", "pela", "pelos", "pelas", "com", "sem", "ao", "aos", "à", "às", "um", "uma",
    "sob", "sobre", "entre",
}
_ROMANO_RE = re.compile(r"^(?=[IVXL])L?X{0,3}(?:IX|IV|V?I{0,3})$")


def _norm_key(texto: Optional[str]) -> str:
    """Chave de comparação: sem acentos, minúscula, só alfanuméricos separados por espaço."""
    if not texto:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", _strip_accents(texto)).strip()


_TITULOS_GENERICOS = frozenset(_norm_key(t) for t in _TITULOS_GENERICOS_RAW)


def truncar_texto(texto: Optional[str], max_chars: int, ellipsis: str = "…") -> str:
    """Trunca o texto em até ``max_chars`` priorizando fim de frase e, depois, fim de palavra."""
    if not texto:
        return ""
    clean = " ".join(texto.split())
    if len(clean) <= max_chars:
        return clean

    janela = clean[: max_chars + 1]
    melhor = -1
    for m in re.finditer(r"[\.!?;](?=\s|$)", janela):
        if m.start() + 1 <= max_chars:
            melhor = m.start()
    if melhor >= int(max_chars * 0.4):
        corte = clean[: melhor + 1]
        return corte[:-1] + "." if corte.endswith(";") else corte

    limite = max(1, max_chars - len(ellipsis))
    espaco = clean[: limite + 1].rfind(" ")
    base = clean[:espaco] if espaco > 0 else clean[:limite]
    return base.rstrip(" ,;:-–—/") + ellipsis


def truncar_titulo(texto: str, max_chars: int) -> str:
    """Trunca títulos em fronteira de palavra, sem reticências e sem separadores pendurados."""
    clean = " ".join(texto.split())
    if len(clean) <= max_chars:
        return clean
    espaco = clean[: max_chars + 1].rfind(" ")
    base = clean[:espaco] if espaco > 0 else clean[:max_chars]
    return base.rstrip(" ,;:-–—/(")


def limpar_texto_documento(texto: Optional[str]) -> str:
    """Remove cabeçalhos/rodapés do SEI/DOU, numeração de páginas e linhas vazias redundantes."""
    if not texto:
        return ""
    clean = texto.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    clean = _NOISE_LINE_RE.sub("", clean)
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n\s*\n+", "\n", clean)
    return clean.strip()


def _juntar_linhas(trecho: str) -> str:
    """Une quebras de linha duras (inclusive hifenização) em texto corrido."""
    trecho = _SUBITEM_RE.sub("", trecho)
    trecho = re.sub(r"(\w)-\n(\w)", r"\1\2", trecho)
    return " ".join(trecho.split())


def extrair_objeto_edital(texto: Optional[str], max_chars: int = MAX_RESUMO_CHARS) -> Optional[str]:
    """Extrai um resumo legível a partir da seção de objeto/finalidade do edital (Issue #77).

    Procura, em ordem de prioridade, seções padronizadas dos editais da UnB
    (``1. DO OBJETO``, ``DO OBJETIVO``, ``DA FINALIDADE``, ``DO PROGRAMA``,
    ``DAS DISPOSIÇÕES PRELIMINARES``), limpa o ruído do SEI/DOU e retorna até
    ``max_chars`` caracteres. Sem seção reconhecível, tenta a fórmula
    "torna pública ..."; caso nada seja encontrado retorna ``None``.
    """
    if not texto or not str(texto).strip():
        return None

    clean = limpar_texto_documento(str(texto))

    for termo in _SECOES_OBJETO:
        secao_re = re.compile(
            rf"^[ \t]*(?:(?:CAP[ÍI]TULO\s+)?{_ENUM}\s*{_SEP}?\s*)?D[OA]S?\s+{termo}\b[ \t]*[:\.\-–—]?[ \t]*",
            re.IGNORECASE | re.MULTILINE,
        )
        m = secao_re.search(clean)
        if not m:
            continue
        restante = clean[m.end():]
        # Cabeçalho composto em caixa alta ("DO OBJETO, HABILITAÇÃO E ...") não faz parte do corpo.
        primeira, _, resto_linhas = restante.partition("\n")
        letras = [c for c in primeira if c.isalpha()]
        if letras and sum(c.isupper() for c in letras) / len(letras) > 0.8:
            restante = resto_linhas
        fim = _PROXIMA_SECAO_RE.search(restante)
        corpo = restante[: fim.start()] if fim else restante[:2000]
        corpo = re.sub(r"\s+\d{1,2}(?:\.\d{1,2})*\.?\s*$", "", corpo)
        corpo = _juntar_linhas(corpo)
        corpo = _CAIXA_ALTA_INICIAL_RE.sub("", corpo)
        if len(corpo) >= 20:
            return truncar_texto(corpo, max_chars)

    corrido = " ".join(clean.split())
    m_pub = _TORNA_PUBLICO_RE.search(corrido)
    if m_pub:
        frase = _PRESENTE_INSTRUMENTO_RE.sub("", m_pub.group(1).strip())
        frase = _BOILERPLATE_FINAL_RE.split(frase, maxsplit=1)[0].strip(" ,;:")
        if len(frase) >= 20:
            frase = frase[0].upper() + frase[1:]
            if not frase.endswith("."):
                frase += "."
            return truncar_texto(frase, max_chars)

    return None


def _tem_termo_especifico(titulo: str) -> bool:
    key = f" {_norm_key(titulo)} "
    if any(f" {termo} " in key for termo in _TERMOS_ESPECIFICOS):
        return True
    siglas = {s.lower() for s in ORGAOS_UNB if "_" not in s}
    return any(f" {sigla} " in key for sigla in siglas)


def _parse_sigla_e_generico(clean: str) -> Optional[Tuple[str, str]]:
    """Identifica títulos no formato 'SIGLA - Termo Genérico' (ex.: 'JURAPP - Edital')."""
    partes = [p.strip() for p in re.split(r"\s*[-–—:|]\s*", clean) if p.strip()]
    if len(partes) != 2:
        return None
    for sigla_cand, gen_cand in ((partes[0], partes[1]), (partes[1], partes[0])):
        k_sigla, k_gen = _norm_key(sigla_cand), _norm_key(gen_cand)
        if (
            len(sigla_cand) <= 12
            and " " not in sigla_cand
            and k_sigla
            and k_sigla not in _TITULOS_GENERICOS
            and sigla_cand.upper() not in ORGAOS_UNB
            and k_gen in _TITULOS_GENERICOS
            and not _tem_termo_especifico(gen_cand)
        ):
            return sigla_cand, gen_cand
    return None


def is_vague_title(titulo: Optional[str]) -> bool:
    """Indica se o título é vago/genérico demais para identificar o edital (Issue #106)."""
    if titulo is None:
        return True
    clean = " ".join(str(titulo).split())
    if len(clean) < 15:
        return True

    key = _norm_key(clean)
    if not key or key in _TITULOS_GENERICOS:
        return True

    # Sigla/acrônimo curto isolado com termo genérico (ex.: 'JURAPP - Edital', 'JURAPP – Inscrições abertas').
    if _parse_sigla_e_generico(clean) is not None:
        return True

    # Código técnico sem espaços (HE_UNB_22_2) ou nome de arquivo.
    if re.fullmatch(r"[A-Z0-9_\-]{4,40}", clean) and re.search(r"[_\d]", clean):
        return True
    if " " not in clean and "_" in clean:
        return True
    if re.search(r"\.(?:pdf|docx?|odt|xlsx?)$", clean, re.IGNORECASE):
        return True

    # Etapa administrativa isolada, curta e sem número de edital nem programa/área.
    if (
        any(key == p or key.startswith(p + " ") for p in _STAGE_PREFIXES)
        and len(clean) < 35
        and not _NUMERO_EDITAL_RE.search(clean)
        and not _tem_termo_especifico(clean)
    ):
        return True

    return False


def _case_palavra(core: str, primeira: bool, preservar_maiusculas: bool) -> str:
    if not core:
        return core
    upper = core.upper()
    if upper in SIGLAS_PRESERVADAS:
        return SIGLAS_PRESERVADAS[upper]
    if re.search(r"[/\-–]", core):
        partes = re.split(r"([/\-–])", core)
        return "".join(
            p if p in "/-–" else _case_palavra(p, primeira and i == 0, preservar_maiusculas)
            for i, p in enumerate(partes)
        )
    if any(ch.isdigit() for ch in core):
        return core
    if core.isupper() and len(core) <= 5 and _ROMANO_RE.match(core):
        return core
    if preservar_maiusculas and core.isupper() and len(core) >= 2:
        return core
    lower = core.lower()
    if not primeira and lower in _MINUSCULAS_PT:
        return lower
    return lower[0].upper() + lower[1:]


def title_case_pt(texto: str) -> str:
    """Title Case em português preservando siglas oficiais (UnB, CNPq, PIBIC-AF, Nº...)."""
    texto = re.sub(r"\bN\s*\.?\s*[º°]\.?", "Nº", texto, flags=re.IGNORECASE)
    letras = [c for c in texto if c.isalpha()]
    maioria_maiuscula = bool(letras) and sum(c.isupper() for c in letras) / len(letras) > 0.6
    preservar = not maioria_maiuscula

    resultado: List[str] = []
    inicio_segmento = True
    for token in texto.split():
        if token in ("-", "–", "—", "|", ":"):
            resultado.append(token)
            inicio_segmento = True
            continue
        m = re.match(r"^([\(\[\"'«]*)(.*?)([\)\]\"'».,;:!?]*)$", token)
        lead, core, trail = m.groups() if m else ("", token, "")
        resultado.append(lead + _case_palavra(core, inicio_segmento, preservar) + trail)
        inicio_segmento = trail.endswith(":")
    return " ".join(resultado)


def _rotulo_util(titulo: Optional[str]) -> Optional[str]:
    """Retorna o rótulo de etapa/ato útil do título original (ou None para lixo como '.', 'AQUI')."""
    if not titulo:
        return None
    clean = " ".join(str(titulo).split()).strip()
    upper = re.sub(r"\s+", "-", clean.upper())
    if upper in _PROGRAMAS_ROTULO:
        return SIGLAS_PRESERVADAS.get(upper, upper)
    for prog in ("PIBIC-AF", "PIBIC-EM", "PIBIC", "PIBITI", "PIBEX", "PIBID", "PROIC"):
        prog_space = prog.replace("-", " ")
        if clean.upper().startswith((prog + " ", prog_space + " ")):
            resto = clean[len(prog):].strip(" -–")
            return f"{prog} {title_case_pt(resto)}".strip()
    par_sigla = _parse_sigla_e_generico(clean)
    if par_sigla is not None:
        sigla_raw, gen_raw = par_sigla
        sigla_fmt = SIGLAS_PRESERVADAS.get(sigla_raw.upper(), sigla_raw.upper() if sigla_raw.isupper() else title_case_pt(sigla_raw))
        rot_gen = _rotulo_util(gen_raw)
        if sigla_raw.upper() in ORGAOS_UNB and sigla_raw.upper() not in _PROGRAMAS_ROTULO:
            return rot_gen
        return f"{sigla_fmt} - {rot_gen}" if rot_gen else sigla_fmt
    key = _norm_key(clean)
    for prefixo, rotulo in _ROTULOS_UTEIS:
        if key == prefixo or key.startswith(prefixo + " "):
            return rotulo
    return None


def _limpar_assunto(assunto: Optional[str], titulo_original: Optional[str] = None) -> Optional[str]:
    """Higieniza o assunto do scraper, descartando valores genéricos e truncando textos longos."""
    if not assunto:
        return None
    clean = " ".join(str(assunto).split()).strip(" -–|:;,.")
    key = _norm_key(clean)
    if len(clean) < 4 or not key or key in _TITULOS_GENERICOS:
        return None
    if re.fullmatch(r"edital(?: [a-z0-9]{2,15})?", key):
        return None
    if titulo_original and key == _norm_key(titulo_original):
        return None
    return truncar_titulo(clean, _MAX_ASSUNTO_TITULO_CHARS)


def _titulo_do_arquivo(url_pdf: Optional[str]) -> Optional[str]:
    """Deriva um título legível do nome do arquivo do PDF (decodificando URL encoding)."""
    if not url_pdf:
        return None
    try:
        path = urlparse(str(url_pdf)).path
    except ValueError:
        return None
    nome = unquote(path.rsplit("/", 1)[-1])
    nome = re.sub(r"\.(?:pdf|docx?|odt|xlsx?)$", "", nome, flags=re.IGNORECASE)
    nome = " ".join(re.sub(r"[-_+]+", " ", nome).split())
    palavras = [p for p in nome.split() if re.fullmatch(r"[^\W\d_]{3,}", p)]
    if len(palavras) < 2:
        return None
    return truncar_titulo(nome, _MAX_ASSUNTO_TITULO_CHARS)


def _assunto_do_objeto(objeto: Optional[str]) -> Optional[str]:
    """Converte o trecho do objeto em um assunto curto para compor o título."""
    if not objeto:
        return None
    s = re.sub(
        r"^(?:o|a)\s+presente\s+(?:edital|chamada|processo)[^,]*?\s+"
        r"(?:tem\s+(?:por|como)\s+(?:objeto|objetivo|finalidade)|visa|destina-se|objetiva)\s+(?:[aà]\s+|o\s+)?",
        "",
        objeto.strip(),
        flags=re.IGNORECASE,
    )
    s = re.sub(r"^(?:o|a|os|as)\s+", "", s, flags=re.IGNORECASE)
    s = re.split(r"[,;.(:]", s, maxsplit=1)[0].strip()
    s = truncar_titulo(s, _MAX_SUBJECT_CHARS)
    palavras = s.split()
    while palavras and palavras[-1].lower() in _MINUSCULAS_PT:
        palavras.pop()
    s = " ".join(palavras)
    if len(s) < 8:
        return None
    return s[0].upper() + s[1:]


def _cabecalho_eh_numerico(cabecalho: str) -> bool:
    """True quando o cabeçalho só traz tipo + número (ex.: 'EDITAL Nº 158/2024')."""
    resto = re.sub(r"\d+|[/\.\-–—º°:]", " ", cabecalho)
    ignorar = {"edital", "chamada", "publica", "aviso", "portaria", "n", "no", "unb", "de", "do", "da"}
    ignorar |= {s.lower() for s in ORGAOS_UNB}
    palavras = [p for p in _norm_key(resto).split() if len(p) >= 3 and p not in ignorar]
    return not palavras


def _extrair_cabecalho(texto: Optional[str]) -> Optional[str]:
    """Localiza o cabeçalho oficial (ex.: 'EDITAL DEG/UnB Nº 12/2025 - ...') no início do texto."""
    if not texto:
        return None
    clean = limpar_texto_documento(str(texto)[: _CABECALHO_JANELA_CHARS * 2])[:_CABECALHO_JANELA_CHARS]
    for m in _CABECALHO_RE.finditer(clean):
        cabecalho = " ".join(m.group(1).split()).strip(" -–:;,.")
        tem_numero = bool(_NUMERO_EDITAL_RE.search(cabecalho) or re.search(r"N\s*\.?\s*[º°]", cabecalho))
        if len(cabecalho) < 10 or (not tem_numero and len(cabecalho.split()) < 3):
            continue
        if not _cabecalho_eh_numerico(cabecalho):
            return cabecalho
        # Cabeçalho só numérico: tenta a linha seguinte (comumente o assunto em caixa alta).
        seguinte = clean[m.end():].lstrip("\n").split("\n", 1)[0].strip()
        letras = [c for c in seguinte if c.isalpha()]
        if (
            10 <= len(seguinte) <= 140
            and letras
            and sum(c.isupper() for c in letras) / len(letras) > 0.8
            and not _PROXIMA_SECAO_RE.match(seguinte)
            and not re.match(rf"^\s*{_ENUM}\s*{_SEP}", seguinte)
        ):
            return f"{cabecalho} - {seguinte.strip(' -–:;,.')}"
        return cabecalho
    return None


def _contem_orgao(titulo: str, orgao: str) -> bool:
    key_titulo = f" {_norm_key(titulo)} "
    key_orgao = _norm_key(orgao.replace("_", " "))
    return bool(key_orgao) and f" {key_orgao} " in key_titulo


def reconstruir_titulo_edital(
    titulo_original: Optional[str],
    texto_extraido: Optional[str] = None,
    assunto: Optional[str] = None,
    orgao_emissor: Optional[str] = None,
    url_pdf: Optional[str] = None,
) -> str:
    """Reconstrói um título claro para editais com título vago/genérico (Issue #106).

    Títulos já informativos são devolvidos sem alterações (apenas ``strip``). Para
    títulos vagos, compõe: rótulo útil da etapa (``Resultado Final``...), cabeçalho
    oficial do PDF (combinado com o objeto quando só numérico), ``assunto`` higienizado,
    nome do arquivo do PDF e, por fim, o órgão emissor — em Title Case com siglas
    preservadas e no máximo ``MAX_TITULO_CHARS`` caracteres.
    """
    if not is_vague_title(titulo_original):
        return str(titulo_original).strip()

    rotulo = _rotulo_util(titulo_original)
    assunto_limpo = _limpar_assunto(assunto, titulo_original)

    contexto: Optional[str] = None
    cabecalho = _extrair_cabecalho(texto_extraido)
    if cabecalho:
        contexto = title_case_pt(cabecalho)
        if _cabecalho_eh_numerico(cabecalho):
            subject = _assunto_do_objeto(extrair_objeto_edital(texto_extraido)) or assunto_limpo
            if subject:
                contexto = f"{contexto} - {title_case_pt(subject)}"
    elif assunto_limpo:
        contexto = title_case_pt(assunto_limpo)
    else:
        subject = _assunto_do_objeto(extrair_objeto_edital(texto_extraido))
        if subject:
            contexto = title_case_pt(subject)
        else:
            nome_arquivo = _titulo_do_arquivo(url_pdf)
            if nome_arquivo:
                contexto = title_case_pt(nome_arquivo)

    if rotulo and contexto:
        key_ctx = _norm_key(contexto)
        key_rot = _norm_key(rotulo)
        titulo = contexto if key_ctx.startswith(key_rot) else f"{rotulo} - {contexto}"
    else:
        titulo = rotulo or contexto or "Edital"

    sufixo = ""
    orgao = (orgao_emissor or "").strip()
    if orgao and not _contem_orgao(titulo, orgao):
        sufixo = f" - {orgao.replace('_', ' ')}"
    titulo = truncar_titulo(titulo, MAX_TITULO_CHARS - len(sufixo)) + sufixo

    if titulo == "Edital" and not orgao:
        return "Edital sem título"
    return titulo
