"""Módulo extensível de parsing e extração de metadados de editais da UnB.

Capaz de analisar o texto e tabelas extraídos de PDFs para identificar:
- Órgão emissor da UnB (DEG, DPG, DEX, DPI, DAC, INT, PROIC, DACES, BCE);
- Período de inscrição (data de início e término);
- Datas de resultado preliminar e final;
- Campus mencionado (Darcy Ribeiro, FGA, FCE, FUP);
- Vagas e indicação de bolsas remuneradas.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

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

# Órgãos e Decanatos da UnB mapeados para extensibilidade
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
    - '14 de outubro de 2026' (data única -> início e fim iguais)
    - '14/10/2026'
    """
    if not text or not text.strip():
        return None, None

    clean = text.strip()

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

    # 2. '23 a 30 de setembro de 2026' (mesmo mês)
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
    clean = _strip_accents(text)

    # Prioriza cabeçalho das primeiras 2000 letras onde o emissor normalmente se declara
    header = clean[:2500]

    for orgao, termos in ORGAOS_UNB.items():
        for termo in termos:
            # Termos curtos como 'deg' usam fronteira de palavra
            if len(termo) <= 4:
                if re.search(rf"\b{re.escape(termo)}\b", header):
                    return orgao
            elif termo in header:
                return orgao

    # Se não achou no cabeçalho, procura no documento inteiro
    for orgao, termos in ORGAOS_UNB.items():
        for termo in termos:
            if len(termo) <= 4:
                if re.search(rf"\b{re.escape(termo)}\b", clean):
                    return orgao
            elif termo in clean:
                return orgao

    return None


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
    """Identifica se há oferta de bolsa remunerada e seu valor monetário."""
    clean = text.lower()
    valor_bolsa: Optional[float] = None
    tem_bolsa: Optional[bool] = None

    # Procura valor monetário em R$
    m_val = re.search(r"r\$\s*([\d\.]+,\d{2})", clean)
    if m_val:
        raw_val = m_val.group(1).replace(".", "").replace(",", ".")
        try:
            valor_bolsa = float(raw_val)
            tem_bolsa = True
        except ValueError:
            pass

    if tem_bolsa is None:
        if any(w in clean for w in ["bolsa remunerada", "bolsista remunerado", "auxílio financeiro", "auxilio financeiro"]):
            tem_bolsa = True
        elif any(w in clean for w in ["voluntário", "voluntario", "sem remuneração", "nao remunerado"]):
            tem_bolsa = False

    return tem_bolsa, valor_bolsa


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
) -> EditalMetadados:
    """Extrai metadados completos de um documento de edital.

    Args:
        doc: Objeto PDFDocumentExtraction (contendo texto e tabelas) ou string de texto simples.
        ano_referencia: Ano do edital para desambiguação de datas quando não explícito no texto.

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
