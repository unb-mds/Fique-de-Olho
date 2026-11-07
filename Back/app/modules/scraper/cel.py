"""Scraper para a CEL / Esporte UnB (Coordenação de Esporte e Lazer da UnB).

Coleta e categoriza editais, chamadas públicas, processos seletivos esportivos,
Bolsa Atleta Universitária, seletivas para os Jogos Universitários Brasileiros (JUBs),
Auxílio Viagem Individual (AVI Esporte/Cultura) e ações do DEAC/DAC.

Fontes oficiais:
- Portal Institucional Esporte UnB (CEL):
  https://esporte.unb.br/
  https://esporte.unb.br/editais/
  https://esporte.unb.br/bolsa-atleta
- Diretoria de Esporte e Atividades Comunitárias (DEAC/DAC):
  https://deac.unb.br/editais-dac/
"""

from __future__ import annotations

from datetime import datetime, timezone
import html as html_lib
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

CEL_BASE_URL = "https://esporte.unb.br"
CEL_EDITAIS_URL = "https://esporte.unb.br/editais/"
CEL_BOLSA_URL = "https://esporte.unb.br/bolsa-atleta"
DEAC_EDITAIS_URL = "https://deac.unb.br/editais-dac/"

DEFAULT_TIMEOUT = 20.0
CACHE_TTL_SECONDS = 300.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Fique-de-Olho/1.0"
)

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".zip", ".odt", ".xlsx", ".xls")
DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
DATE_ISO_PATTERN = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
DATE_PT_PATTERN = re.compile(
    r"\b(\d{1,2})\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|"
    r"julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(20\d{2})\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

MESES_PT_NUM = {
    "janeiro": "01",
    "fevereiro": "02",
    "marco": "03",
    "março": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def _current_year() -> int:
    """Retorna o ano corrente em UTC para execuções periódicas automatizadas."""
    return datetime.now(timezone.utc).year


def _clean_str(text: Optional[str]) -> str:
    if not text:
        return ""
    unescaped = html_lib.unescape(text)
    return " ".join(unescaped.strip().split())


def _is_doc_or_form(url: str) -> bool:
    if not url:
        return False
    u_lower = url.lower()
    return (
        any(u_lower.endswith(ext) or ext in u_lower for ext in DOC_EXTENSIONS)
        or "drive.google.com" in u_lower
        or "docs.google.com" in u_lower
    )


def classify_cel_document(title: str, link: str) -> str:
    """Classifica o tipo de documento anexo para editais da CEL/DEAC."""
    t_low = (title or "").lower()
    l_low = (link or "").lower()
    combined = f"{t_low} {l_low}"

    if "resultado final" in combined or "resultado_final" in combined or "resultado definitivo" in combined:
        return "resultado_final"
    if "resultado preliminar" in combined or "resultado provisório" in combined or "resultado_provisorio" in combined or "preliminar" in combined:
        return "resultado_provisorio"
    if "retifica" in combined or "errata" in combined:
        return "retificacao"
    if "homologa" in combined or "convoca" in combined or "lista" in combined:
        return "resultado_provisorio"
    return classify_document(title, link)


def _extract_date_str(text: str, fallback_year: int) -> str:
    """Extrai uma representação de data em formato DD/MM/AAAA ou ISO."""
    if not text:
        return f"01/01/{fallback_year}"
    m_slash = DATE_SLASH_PATTERN.search(text)
    if m_slash:
        dia, mes, ano = int(m_slash.group(1)), int(m_slash.group(2)), int(m_slash.group(3))
        return f"{dia:02d}/{mes:02d}/{ano}"

    m_pt = DATE_PT_PATTERN.search(text)
    if m_pt:
        dia = int(m_pt.group(1))
        mes_raw = m_pt.group(0).lower()
        ano = int(m_pt.group(2))
        for m_nome, m_num in MESES_PT_NUM.items():
            if m_nome in mes_raw:
                return f"{dia:02d}/{m_num}/{ano}"

    m_iso = DATE_ISO_PATTERN.search(text)
    if m_iso:
        ano, mes, dia = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return f"{dia:02d}/{mes:02d}/{ano}"

    m_year = YEAR_PATTERN.search(text)
    if m_year:
        return f"01/01/{m_year.group(1)}"

    return f"01/01/{fallback_year}"


def _infer_cel_category(title: str, text: str = "") -> str:
    comb = f"{title} {text}".lower()
    if "bolsa" in comb or "auxílio" in comb or "auxilio" in comb or "avi" in comb or "atleta" in comb:
        return "Bolsas / Auxílios"
    if "estágio" in comb or "estagio" in comb:
        return "Estágio"
    return "Extensões"


def _infer_cel_tipo_edital(title: str) -> str:
    t_low = title.lower()
    if "bolsa atleta" in t_low or "atleta" in t_low:
        return "Bolsa Atleta"
    if "auxílio viagem" in t_low or "auxilio viagem" in t_low or "avi" in t_low:
        return "Auxílio Viagem Individual (AVI)"
    if "aprafe" in t_low:
        return "APRAFE Esporte e Cultura"
    if "jubs" in t_low or "compet" in t_low or "seletiv" in t_low:
        return "Seletiva Esportiva / JUBs"
    if "eletrônico" in t_low or "eletronico" in t_low or "esportes eletrônicos" in t_low:
        return "Esportes Eletrônicos"
    if "chamada" in t_low:
        return "Chamada Pública"
    return "Edital Esportivo"


def _clean_edital_title(title: str) -> str:
    """Higieniza prefixos de anexos/resultados para manter o título focado no edital."""
    cleaned = re.sub(
        r"^(?:resultado\s+(?:final|preliminar|provis[óo]rio|definitivo)|retifica[çc][ãa]o(?:\s+n[ºo.]?\s*\d+)?|errata(?:\s+n[ºo.]?\s*\d+)?|anexo\s+[ivx\d]+|comunicado(?:\s+n[ºo.]?\s*\d+)?)\s*[–—\-:\.]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or title


def _normalize_group_key(raw_title: str) -> str:
    """Extrai uma chave canônica de agrupamento do edital (ex: Edital nº 08/2025/DAC)."""
    t = raw_title.lower()
    cleaned = re.sub(
        r"^(?:edital(?:\s+dac)?(?:\s+n[ºo.]?\s*[\d.]+(?:[/-][\d.]+)?(?:/dac)?)?|chamada\s+p[úu]blica(?:\s+n[ºo.]?\s*[\d.]+(?:[/-][\d.]+)?(?:/dac)?)?|resultado\s+(?:final|preliminar|provis[óo]rio|definitivo)|retifica[çc][ãa]o(?:\s+n[ºo.]?\s*[\d.]+)?|errata(?:\s+n[ºo.]?\s*[\d.]+)?|anexo\s+[ivx\d]+|comunicado(?:\s+n[ºo.]?\s*[\d.]+)?)\s*[–—\-:\.]\s*",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"^(?:para\s+(?:a\s+)?|de\s+|do\s+|da\s+|a\s+)", "", cleaned).strip()

    if "auxílio viagem" in cleaned or "auxilio viagem" in cleaned or "avi" in cleaned:
        m_yr = YEAR_PATTERN.search(cleaned)
        yr = m_yr.group(1) if m_yr else ""
        return f"auxilio viagem individual {yr}".strip()
    if "bolsa atleta" in cleaned:
        m_yr = YEAR_PATTERN.search(cleaned)
        yr = m_yr.group(1) if m_yr else ""
        return f"bolsa atleta {yr}".strip()
    if "aprafe" in cleaned:
        m_yr = YEAR_PATTERN.search(cleaned)
        yr = m_yr.group(1) if m_yr else ""
        return f"aprafe {yr}".strip()
    if "meca" in cleaned:
        m_yr = YEAR_PATTERN.search(cleaned)
        yr = m_yr.group(1) if m_yr else ""
        return f"iniciativa meca {yr}".strip()
    if "seleção de bolsistas" in cleaned or "selecao de bolsistas" in cleaned:
        m_yr = YEAR_PATTERN.search(cleaned)
        yr = m_yr.group(1) if m_yr else ""
        return f"selecao de bolsistas {yr}".strip()
    if "eletrônico" in cleaned or "eletronico" in cleaned or "representação" in cleaned or "representacao" in cleaned:
        m_yr = YEAR_PATTERN.search(cleaned)
        yr = m_yr.group(1) if m_yr else ""
        return f"esportes representacao eletronicos {yr}".strip()

    m_edital = re.search(r"(edital\s+(?:dac\s+)?(?:n[ºo.]?\s*)?\d+(?:[/-]\d+)?)", cleaned)
    if m_edital:
        return re.sub(r"\s+", " ", m_edital.group(1).strip())
    m_chamada = re.search(r"(chamada\s+p[úu]blica\s+(?:n[ºo.]?\s*)?\d+(?:[/-]\d+)?)", cleaned)
    if m_chamada:
        return re.sub(r"\s+", " ", m_chamada.group(1).strip())

    return re.sub(r"[^a-z0-9]+", "", cleaned[:45])


def _is_generic_doc_label(text: str) -> bool:
    """Verifica se o texto do link é apenas um rótulo genérico de anexo/resultado/etapa."""
    t = _clean_str(text).lower()
    if not t:
        return True
    generic_exact = {
        "edital",
        "edital de abertura",
        "resultado",
        "resultado final",
        "resultado provisório",
        "resultado provisorio",
        "resultado preliminar",
        "resultados finais",
        "resultado do edital",
        "retificação",
        "retificacao",
        "errata",
        "inscrições",
        "inscricoes",
        "inscrição",
        "inscricao",
        "formulário de inscrição",
        "formulario de inscricao",
        "formulário de inscrições",
        "formulario de inscricoes",
        "homologação das inscrições",
        "homologacao das inscricoes",
        "frequência",
        "frequencia",
        "regulamento",
        "termo de compromisso",
        "termo de responsabilidade",
        "termo aditivo",
    }
    if t in generic_exact:
        return True
    generic_prefixes = (
        "resultado ",
        "resultados ",
        "retificação",
        "retificacao",
        "1ª retificação",
        "2ª retificação",
        "3ª retificação",
        "errata",
        "anexo ",
        "nota informativa",
        "comunicado",
        "homologação",
        "homologacao",
        "processo nº",
        "processo n°",
        "processo n.",
        "inscrições",
        "inscricoes",
        "formulário",
        "formulario",
        "frequência",
        "frequencia",
        "prazo para assinatura",
        "interposição de recursos",
        "interposicao de recursos",
        "termo ",
        "recomendação",
        "recomendacao",
        "atestado de convocação",
        "atestado de convocacao",
        "seleção complementar",
        "selecao complementar",
        "segunda chamada",
        "reabertura",
        "prorrogação",
        "prorrogacao",
    )
    return t.startswith(generic_prefixes)


def _is_section_heading_text(text: str) -> bool:
    """Identifica se um parágrafo/div sem links funciona como cabeçalho de seção de um edital."""
    t = _clean_str(text)
    if not t or len(t) < 5 or len(t) > 350:
        return False
    tl = t.lower()
    if re.match(r"^editais\s+20\d{2}$", tl):
        return False
    if "informamos que, a partir do ano" in tl or "não há artigos nesta categoria" in tl:
        return False
    if set(t).issubset({"—", "–", "-", " ", "_"}):
        return False
    keywords = (
        "edital",
        "chamada",
        "programa",
        "seleção",
        "selecao",
        "bolsa",
        "auxílio",
        "auxilio",
        "aprafe",
        "estafe",
        "torneio",
        "curso de árbitro",
        "curso de arbitro",
        "oficinas",
        "finca",
        "circuito cultural",
    )
    return any(k in tl for k in keywords)


def _compose_edital_title(heading: str, candidate_title: str) -> str:
    """Combina o cabeçalho da seção com o título do documento principal quando apropriado."""
    h = _clean_str(heading).rstrip("–—-: ")
    c = _clean_str(candidate_title.replace("_", " "))
    if not h:
        return _clean_edital_title(c)
    if not c or _is_generic_doc_label(c):
        return _clean_edital_title(h)
    cl = c.lower()
    hl = h.lower()
    # Se o candidato já inicia com "Edital Nº..." ou "Chamada Pública Nº...", ele já é autoexplicativo
    if re.search(r"^(?:edital|chamada\s+p[úu]blica)\s+(?:dac\s+|deac\s+|del/dac\s+)?(?:n[ºo°.]?\s*)?\d", cl):
        return _clean_edital_title(c)
    if hl in cl:
        return _clean_edital_title(c)
    if cl in hl:
        return _clean_edital_title(h)
    # Remove trecho de "Processo Nº..." do cabeçalho ao concatenar para ficar limpo
    h_short = re.sub(r"\s*[–—\-]?\s*processo\s+n[ºo°.]?\s*[\d./-]+", "", h, flags=re.IGNORECASE).strip(" –—-:")
    if h_short and h_short.lower() not in cl:
        return f"{h_short} – {_clean_edital_title(c)}"
    return _clean_edital_title(c)


def _parse_tabbed_portal_html(
    html: str,
    base_url: str,
    reference_year: Optional[int],
    assunto_prefix: str,
    programa_label: str,
) -> List[Dict[str, Any]]:
    """Parser unificado para páginas estruturadas em abas Elementor (esporte.unb.br e deac.unb.br)."""
    curr_yr = reference_year or _current_year()
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []

    tab_wrappers = soup.find_all("div", class_=lambda c: c and "elementor-tab-content" in c)
    if not tab_wrappers:
        content_divs = [
            d for d in soup.find_all("div", class_=lambda c: c and ("entry-content" in c or "elementor-widget" in c))
            if d.find("a", href=True)
        ]
        tab_wrappers = content_divs if content_divs else [soup]

    for idx_tab, tab in enumerate(tab_wrappers):
        tab_id = tab.get("id", "")
        data_tab = tab.get("data-tab", "")
        tab_title_elem = None
        if tab_id:
            tab_title_elem = soup.find("div", {"aria-controls": tab_id})
            if not tab_title_elem and len(tab_id) >= 4:
                tab_title_elem = soup.find("div", id=f"elementor-tab-title-{tab_id[-4:]}")
        if not tab_title_elem and data_tab:
            tab_title_elem = soup.find("div", class_="elementor-tab-title", attrs={"data-tab": data_tab})

        tab_year_str = tab_title_elem.get_text(strip=True) if tab_title_elem else ""
        m_tab_title_yr = YEAR_PATTERN.search(tab_year_str)
        m_yr = m_tab_title_yr or YEAR_PATTERN.search(tab.get_text()[:200])
        has_explicit_tab_year = m_yr is not None
        tab_year = int(m_yr.group(1)) if m_yr else curr_yr

        # Percorre elementos folha de bloco em ordem DOM
        blocks = [
            el for el in tab.find_all(["p", "li", "h2", "h3", "h4", "div"])
            if el.name != "div" or not el.find(["p", "ul", "li", "div", "h2", "h3", "h4"])
        ]
        if not blocks:
            blocks = [tab]

        grouped_items: Dict[str, Dict[str, Any]] = {}
        active_heading: str = ""
        active_group_key: Optional[str] = None
        heading_counter = 0

        for blk in blocks:
            blk_text = _clean_str(blk.get_text(" ", strip=True))
            a_tags = blk.find_all("a", href=True)

            if not a_tags:
                if blk.name in ("p", "h2", "h3", "h4", "div") and _is_section_heading_text(blk_text):
                    active_heading = blk_text
                    heading_counter += 1
                    active_group_key = f"sec_{idx_tab}_{heading_counter}_{_normalize_group_key(blk_text)}"
                continue

            for a in a_tags:
                raw_href = a["href"].strip()
                link_href = urljoin(base_url, raw_href)
                link_text = _clean_str(a.get_text(" ", strip=True))
                if not link_text:
                    link_text = blk_text or "Documento Esporte UnB"

                # Ignora links institucionais ou de redirecionamento geral
                if any(
                    x in link_href.lower()
                    for x in [
                        "deac.unb.br/editais-dac",
                        "estatuto",
                        "regimento",
                        "politica_de_cookies",
                        "telefones",
                        "instagram.com",
                        "facebook.com",
                    ]
                ):
                    continue

                is_doc = _is_doc_or_form(link_href)
                is_deac_edital_page = "deac.unb.br/" in link_href.lower() and "edital" in link_href.lower()
                if not is_doc and not is_deac_edital_page and not any(
                    k in link_href.lower() or k in link_text.lower()
                    for k in ["edital", "resultado", "chamada", "bolsa", "anexo", "selecao", "aprafe", "meca", "avi", "esporte"]
                ):
                    continue

                is_form_only = "docs.google.com/forms" in link_href.lower() or "forms.gle" in link_href.lower()
                is_generic = _is_generic_doc_label(link_text)

                # Decide a chave de agrupamento
                if active_group_key and active_group_key.startswith("sec_") and blk.name == "li":
                    # Dentro de uma lista <ul> precedida por cabeçalho de seção explícito
                    group_key = active_group_key
                elif is_generic and active_group_key:
                    group_key = active_group_key
                else:
                    norm_k = _normalize_group_key(link_text) or _normalize_group_key(blk_text) or link_href
                    # Verifica se já pertence ao grupo ativo
                    if active_group_key and active_group_key.endswith(f"_{norm_k}"):
                        group_key = active_group_key
                    else:
                        group_key = norm_k
                        if not is_generic:
                            active_group_key = group_key
                            if blk.name in ("p", "h2", "h3", "h4"):
                                active_heading = link_text

                m_link_yr = YEAR_PATTERN.search(link_text) or YEAR_PATTERN.search(active_heading)
                if not m_link_yr and not has_explicit_tab_year:
                    m_link_yr = YEAR_PATTERN.search(link_href)
                item_year = int(m_link_yr.group(1)) if m_link_yr else tab_year

                if group_key not in grouped_items:
                    grouped_items[group_key] = {
                        "heading": active_heading if group_key.startswith("sec_") else "",
                        "main_title": link_text if not is_generic else (active_heading or link_text),
                        "canonical_link": link_href,
                        "year": item_year,
                        "docs": [],
                        "link_inscricao": None,
                        "has_resultado_final": False,
                    }

                doc_type = classify_cel_document(link_text, link_href)
                if doc_type == "resultado_final":
                    grouped_items[group_key]["has_resultado_final"] = True

                if is_form_only or "inscric" in link_text.lower():
                    if not grouped_items[group_key]["link_inscricao"]:
                        grouped_items[group_key]["link_inscricao"] = link_href

                # Se for apenas um Google Forms e o edital já possuir PDFs, mantém apenas em link_inscricao
                if not is_form_only:
                    grouped_items[group_key]["docs"].append({
                        "titulo": link_text,
                        "link": link_href,
                        "tipo": doc_type,
                    })
                elif not grouped_items[group_key]["docs"]:
                    grouped_items[group_key]["docs"].append({
                        "titulo": link_text,
                        "link": link_href,
                        "tipo": doc_type,
                    })

                if not is_generic and doc_type == "original":
                    grouped_items[group_key]["canonical_link"] = link_href
                    grouped_items[group_key]["main_title"] = link_text

        for key, g in grouped_items.items():
            # Remove Google Forms da lista de documentos caso outros PDFs tenham sido adicionados ao grupo
            if len(g["docs"]) > 1:
                non_form_docs = [
                    d for d in g["docs"]
                    if "docs.google.com/forms" not in d["link"].lower() and "forms.gle" not in d["link"].lower()
                ]
                if non_form_docs:
                    g["docs"] = non_form_docs

            candidates = [
                d for d in g["docs"]
                if not _is_generic_doc_label(d["titulo"])
            ]
            if candidates:
                best_doc = candidates[0]
                edital_title = _compose_edital_title(g["heading"], best_doc["titulo"])
                g["canonical_link"] = best_doc["link"]
            elif g["docs"]:
                edital_title = _compose_edital_title(g["heading"], g["docs"][0]["titulo"])
                g["canonical_link"] = g["docs"][0]["link"]
            else:
                edital_title = _compose_edital_title(g["heading"], g["main_title"])

            ed_year = g["year"]
            m_ed_yr = YEAR_PATTERN.search(edital_title) or YEAR_PATTERN.search(g["heading"])
            if m_ed_yr:
                ed_year = int(m_ed_yr.group(1))

            date_pub = _extract_date_str(edital_title, ed_year)
            status = "fechado" if (g["has_resultado_final"] or ed_year < curr_yr) else "aberto"
            tipo_cat = _infer_cel_category(edital_title)
            tipo_ed = _infer_cel_tipo_edital(edital_title)

            final_docs = g["docs"]
            if not final_docs and _is_doc_or_form(g["canonical_link"]):
                final_docs = [{
                    "titulo": edital_title,
                    "link": g["canonical_link"],
                    "tipo": classify_cel_document(edital_title, g["canonical_link"]),
                }]

            editais.append({
                "titulo": edital_title,
                "assunto": f"{assunto_prefix} — {tipo_ed}",
                "tipo": tipo_cat,
                "tipo_edital": tipo_ed,
                "programa": programa_label,
                "descricao": f"Processo seletivo e edital publicado por {programa_label}: {edital_title}.",
                "resumo": f"Edital publicado por {programa_label} ({ed_year}): {edital_title}.",
                "unidade": "CEL",
                "campus": "Darcy Ribeiro",
                "link": g["canonical_link"],
                "link_inscricao": g["link_inscricao"],
                "data_publicacao": date_pub,
                "inicio_inscricao": None,
                "fim_inscricao": None,
                "status": status,
                "ano": ed_year,
                "documentos": final_docs,
            })

    return editais


def parse_cel_editais_html(
    html: str,
    base_url: str = CEL_EDITAIS_URL,
    reference_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Analisa o HTML da página de editais da CEL (com tabs Elementor por ano) e agrupa documentos."""
    return _parse_tabbed_portal_html(
        html=html,
        base_url=base_url,
        reference_year=reference_year,
        assunto_prefix="Esporte Universitário / CEL",
        programa_label="Coordenação de Esporte e Lazer (CEL/UnB)",
    )


def parse_deac_editais_html(
    html: str,
    base_url: str = DEAC_EDITAIS_URL,
    reference_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extrai os editais esportivos e comunitários da DEAC/DAC (página oficial indicada pela CEL)."""
    return _parse_tabbed_portal_html(
        html=html,
        base_url=base_url,
        reference_year=reference_year,
        assunto_prefix="Esporte e Atividades Comunitárias / DEAC-DAC",
        programa_label="Diretoria de Esporte e Atividades Comunitárias (DEAC/DAC/CEL)",
    )


class CELScraper(BaseScraper):
    """Scraper para o portal de editais esportivos e Bolsa Atleta da Coordenação de Esporte e Lazer (CEL/UnB)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "CEL"

    def _cache_set(self, url: str, docs: List[Dict[str, Any]]) -> None:
        self._url_to_docs_cache[url] = (time.time(), docs)

    def _cache_get(self, url: str) -> Optional[List[Dict[str, Any]]]:
        item = self._url_to_docs_cache.get(url)
        if not item:
            return None
        ts, docs = item
        if time.time() - ts > CACHE_TTL_SECONDS:
            self._url_to_docs_cache.pop(url, None)
            return None
        return docs

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Coleta editais e chamadas esportivas da CEL (esporte.unb.br e deac.unb.br)."""
        self._url_to_docs_cache.clear()
        curr_year = _current_year()
        editais: List[Dict[str, Any]] = []
        seen_links = set()
        seen_titles = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Coleta do portal oficial esporte.unb.br/editais/
                try:
                    resp_cel = client.get(CEL_EDITAIS_URL)
                    if resp_cel.status_code == 200:
                        cel_items = parse_cel_editais_html(resp_cel.text, base_url=str(resp_cel.url), reference_year=curr_year)
                        for item in cel_items:
                            self._cache_set(item["link"], item.get("documentos", []))
                            norm_t = re.sub(r"[^a-z0-9]+", "", item["titulo"].lower())
                            if item["link"] in seen_links or norm_t in seen_titles:
                                continue
                            if year is not None and item.get("ano") != year:
                                continue
                            seen_links.add(item["link"])
                            seen_titles.add(norm_t)
                            editais.append(item)
                except httpx.HTTPError as exc:
                    logger.warning(f"[CEL] Erro ao acessar {CEL_EDITAIS_URL}: {exc}")

                # 2. Coleta de deac.unb.br/editais-dac/ (editais vigentes da DEAC/CEL)
                try:
                    resp_deac = client.get(DEAC_EDITAIS_URL)
                    if resp_deac.status_code == 200:
                        deac_items = parse_deac_editais_html(resp_deac.text, base_url=str(resp_deac.url), reference_year=curr_year)
                        for item in deac_items:
                            norm_t = re.sub(r"[^a-z0-9]+", "", item["titulo"].lower())
                            if norm_t in seen_titles:
                                continue
                            if item["link"] in seen_links:
                                # Se houver colisão de URL principal mas outro anexo inédito pertencer ao edital, promove-o
                                alt_links = [
                                    d["link"] for d in item.get("documentos", [])
                                    if d.get("link") and d["link"] not in seen_links
                                ]
                                if alt_links:
                                    item["link"] = alt_links[0]
                                else:
                                    continue
                            self._cache_set(item["link"], item.get("documentos", []))
                            if year is not None and item.get("ano") != year:
                                continue
                            seen_links.add(item["link"])
                            seen_titles.add(norm_t)
                            editais.append(item)
                except httpx.HTTPError as exc:
                    logger.warning(f"[CEL] Erro ao acessar {DEAC_EDITAIS_URL}: {exc}")

        except Exception as exc:
            logger.error(f"[CEL] Erro inesperado na coleta: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Recupera ou extrai documentos vinculados a um edital da CEL."""
        if not edital_url:
            return []

        cached = self._cache_get(edital_url)
        if cached is not None:
            return cached

        if _is_doc_or_form(edital_url):
            doc = [{
                "titulo": _clean_str(edital_url.split("/")[-1]),
                "link": edital_url,
                "tipo": classify_cel_document(edital_url, edital_url),
            }]
            self._cache_set(edital_url, doc)
            return doc

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    docs = []
                    for a in soup.find_all("a", href=True):
                        h = urljoin(str(resp.url), a["href"].strip())
                        if any(x in h.lower() for x in ["estatuto", "regimento", "politica_de_cookies"]):
                            continue
                        t = _clean_str(a.get_text(strip=True)) or h.split("/")[-1]
                        if _is_doc_or_form(h):
                            docs.append({
                                "titulo": t,
                                "link": h,
                                "tipo": classify_cel_document(t, h),
                            })
                    # Suporte para páginas de attachment do WordPress com miniatura '-pdf.jpg'
                    if not docs:
                        for img in soup.find_all("img", src=True):
                            src = urljoin(str(resp.url), img["src"].strip())
                            if src.lower().endswith("-pdf.jpg"):
                                pdf_url = re.sub(r"-pdf\.jpg$", ".pdf", src, flags=re.IGNORECASE)
                                title_el = soup.find("h1")
                                t_doc = _clean_str(title_el.get_text(strip=True)) if title_el else pdf_url.split("/")[-1]
                                docs.append({
                                    "titulo": t_doc,
                                    "link": pdf_url,
                                    "tipo": classify_cel_document(t_doc, pdf_url),
                                })
                    self._cache_set(edital_url, docs)
                    return docs
        except Exception as exc:
            logger.warning(f"[CEL] Erro ao buscar documentos em {edital_url}: {exc}")

        return []


cel_scraper = CELScraper()
