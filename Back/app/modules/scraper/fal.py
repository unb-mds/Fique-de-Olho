"""Scraper para a FAL (Fazenda Água Limpa da Universidade de Brasília).

Coleta e categoriza editais, chamadas de fluxo contínuo, oportunidades de estágio
e práticas de campo, submissão de projetos científicos/extensão, laboratórios
experimentais e eventos rurais nas áreas de Agronomia, Engenharia Florestal,
Medicina Veterinária, Zootecnia e Meio Ambiente sediados na Fazenda Água Limpa.

Fontes oficiais:
- Portal Institucional da Fazenda Água Limpa (FAL/UnB):
  https://fal.unb.br/
  https://fal.unb.br/index.php?option=com_content&view=category&layout=blog&id=2
- Portal de Estágios e Editais FAV/FAL (Agronomia, Medicina Veterinária, Saúde Animal e Agronegócios):
  https://fav.unb.br/estagio/
  https://fav.unb.br/wp-json/wp/v2/posts?search=edital&per_page=20
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html as html_lib
import logging
import re
from typing import Any, Dict, List, Optional
import unicodedata
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

FAL_BASE_URL = "https://fal.unb.br"
FAL_BLOG_URL = f"{FAL_BASE_URL}/index.php?option=com_content&view=category&layout=blog&id=2"
FAV_ESTAGIO_URL = "https://fav.unb.br/estagio/"
FAV_EDITAIS_API_URL = "https://fav.unb.br/wp-json/wp/v2/posts?search=edital&per_page=20"

DEFAULT_TIMEOUT = 20.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Fique-de-Olho/1.0"
)

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".zip", ".odt", ".xlsx", ".xls")
DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b")
DATE_ISO_PATTERN = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
DATE_PT_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|"
    r"julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+20\d{2})\b",
    re.IGNORECASE,
)
GENERAL_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
EXPLICIT_PROJECT_TITLE_PATTERN = re.compile(
    r"\bT[íi]tulo(?:\s+do\s+projeto)?\s*:\s*(.+?)(?=\s+(?:Tipo|Coordenador|Orientador|Resumo)\b|$)",
    re.IGNORECASE,
)

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

# Páginas puramente institucionais/estáticas do Joomla da FAL que não configuram
# oportunidade acadêmica, estágio, laboratório prático, chamada ou projeto
STATIC_INSTITUTIONAL_SLUGS = {
    "historico",
    "missao",
    "espaco-fisico",
    "localizacao",
    "diretoria",
    "conselho-deliberativo",
    "restaurante-universitario",
    "transporte",
    "achados-e-perdidos",
    "videos",
    "regimento-interno",
    "faca-sua-doacao",
    "papel-social",
    "fazenda-agua-limpa-da-unb-se-destaca-em-seu-papel-social",
    "coordenadoria-de-seguranca-e-protecao-ambiental",
    "laboratorios",
    "projetos",
}

STATIC_INSTITUTIONAL_TITLES = {
    ".",
    "histórico",
    "historico",
    "missão",
    "missao",
    "espaço físico",
    "espaco fisico",
    "localização",
    "localizacao",
    "diretoria",
    "conselho deliberativo",
    "restaurante universitário",
    "restaurante universitario",
    "transporte",
    "achados e perdidos",
    "vídeos",
    "videos",
    "regimento interno - fal",
    "regimento interno",
    "sua doação faz a diferença!",
    "papel social",
    "laboratórios",
    "coordenadoria de segurança e proteção ambiental",
}

GENERIC_SITE_FOOTER_DOCS = (
    "estatuto_e_regimento",
    "mapas_da_unb",
    "resolucao_cplad",
    "politica_de_cookies",
    "telefones_unb",
)

# Termos de spam externo injetados em páginas legadas de CMS para higienização automática
SPAM_KEYWORDS_PATTERN = re.compile(
    r"\b(?:deneme\s+bonusu|casinos?\s+online|online\s+casinos?|bahis|slot\s+siteleri|sweet\s+bonanza|betting)\b",
    re.IGNORECASE,
)

GENERIC_ACADEMIC_TITLES = {
    "iniciação científica",
    "iniciacao cientifica",
    "doutorado",
    "mestrado",
    "mestrado e iniciação científica",
    "mestrado e iniciacao cientifica",
    "extensão",
    "extensao",
    "projeto de pesquisa",
}


def sanitize_fal_text(raw: str) -> str:
    """Higieniza texto extraído da FAL normalizando Unicode NFC, entidades HTML e trechos de spam SEO."""
    if not raw:
        return ""
    unescaped = unicodedata.normalize("NFC", html_lib.unescape(raw))
    cleaned = re.sub(r"\s+", " ", unescaped).strip()
    if not SPAM_KEYWORDS_PATTERN.search(cleaned):
        return cleaned

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    safe_sentences = [s for s in sentences if not SPAM_KEYWORDS_PATTERN.search(s)]
    return " ".join(safe_sentences).strip()


def _normalize_date_str(raw_date: str, default_year: int = 2026) -> str:
    """Converte datas ISO, por extenso ou com barras para o formato padrão DD/MM/YYYY."""
    if not raw_date:
        return f"01/01/{default_year}"

    m_iso = DATE_ISO_PATTERN.search(raw_date)
    if m_iso:
        return f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"

    m_slash = DATE_SLASH_PATTERN.search(raw_date)
    if m_slash:
        parts = m_slash.group(1).split("/")
        return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"

    m_pt = DATE_PT_PATTERN.search(raw_date)
    if m_pt:
        m_parts = re.match(
            r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(20\d{2})",
            m_pt.group(1).strip(),
            re.IGNORECASE,
        )
        if m_parts:
            day = int(m_parts.group(1))
            month = MESES_PT_NUM.get(m_parts.group(2).lower(), "01")
            year = m_parts.group(3)
            return f"{day:02d}/{month}/{year}"

    return f"01/01/{default_year}"


def is_fal_static_institutional(title: str, href: str) -> bool:
    """Identifica artigos meramente administrativos/institucionais que não são oportunidades ou chamadas."""
    norm_title = re.sub(r"\s+", " ", (title or "").lower()).strip()
    if not norm_title or norm_title in STATIC_INSTITUTIONAL_TITLES:
        return True

    m_slug = re.search(r"[?&]id=\d+:([a-z0-9-]+)", (href or "").lower())
    if m_slug and m_slug.group(1) in STATIC_INSTITUTIONAL_SLUGS:
        return True

    return False


def _match_area_in_snippet(snippet: str) -> Optional[str]:
    """Auxiliar para correspondência de área temática em título ou corpo."""
    low = (snippet or "").lower()
    if any(
        k in low
        for k in [
            "agronomia",
            "agronegócio",
            "agronegocio",
            "propaga",
            "fav/marca",
            "agrícola",
            "agricola",
            "agroclimatologia",
            "hidráulica",
            "hidraulica",
            "mecanização",
            "mecanizacao",
            "lamagri",
            "produtor rural",
            "dia de campo",
            "ppga",
            "bananeira",
            "plantas medicinais",
        ]
    ):
        return "Agronomia e Ciências Agrárias"
    if any(
        k in low
        for k in [
            "florestal",
            "florestais",
            "viveiro",
            "incêndio",
            "incendio",
            "beija fal",
            "beija-fal",
            "cerrado",
            "ecologia",
            "papagaio",
            "zoologia",
            "botânica",
            "botanica",
            "arbóreas",
            "arboreas",
            "besouros",
            "lagartos",
        ]
    ):
        return "Engenharia Florestal e Conservação Ambiental"
    if any(
        k in low
        for k in [
            "suíno",
            "suino",
            "labsui",
            "ovino",
            "cmo",
            "cavalo",
            "equideocultura",
            "equino",
            "equídeo",
            "equideo",
            "reprodução",
            "reproducao",
            "nutrição animal",
            "nutricao animal",
            "embrião",
            "embriao",
            "fertilização in vitro",
            "fertilizacao in vitro",
            "veterinária",
            "veterinaria",
            "saúde animal",
            "saude animal",
            "zootecnia",
            "aquicultura",
            "aquaponia",
            "peixinho",
        ]
    ):
        return "Medicina Veterinária e Produção Animal"
    return None


def detect_fal_area(titulo: str, texto: str = "") -> str:
    """Identifica a área de conhecimento predominante priorizando o título do laboratório/projeto."""
    by_title = _match_area_in_snippet(titulo)
    if by_title:
        return by_title
    by_body = _match_area_in_snippet(texto)
    if by_body:
        return by_body
    return "Ciências Agrárias, Florestais e Ambientais"


def is_fal_document_url(url: str) -> bool:
    """Verifica se a URL aponta para arquivo anexo (.pdf, .docx, etc. ou PhocaDownload do Joomla)."""
    if not url:
        return False
    lower = url.lower()
    parsed = urlparse(lower)
    if parsed.path.endswith(DOC_EXTENSIONS):
        return True
    if "option=com_phocadownload" in lower and "view=file" in lower:
        return True
    return False


def _clean_fal_doc_title(link_text: str, full_link: str) -> str:
    """Normaliza o título de um anexo da FAL/FAV, corrigindo textos truncados ou genéricos."""
    cleaned = sanitize_fal_text(link_text)
    low = cleaned.lower()
    if low == "regulamento de estágio obrigatóri" or low == "regulamento de estagio obrigatori":
        return "Regulamento de Estágio Obrigatório"
    if cleaned and low not in {"clique aqui", "acesse aqui", "acesse aqui o edital", "baixar", "download"}:
        return cleaned

    m_phoca = re.search(r"[?&]id=\d+:([a-z0-9_-]+)", full_link.lower())
    if m_phoca:
        return m_phoca.group(1).replace("-", " ").replace("_", " ").title()

    filename = urlparse(full_link).path.rstrip("/").split("/")[-1]
    return filename or "Documento Oficial FAL/UnB"


def classify_fal_document(title: str, link: str) -> str:
    """Classifica um documento vinculado a uma chamada ou oportunidade da FAL."""
    lower = f"{title} {link}".lower()
    if any(k in lower for k in ["resultado final", "resultado_final", "homologacao", "homologação"]):
        return "resultado_final"
    if any(k in lower for k in ["resultado preliminar", "resultado_preliminar", "resultado provisorio"]):
        return "resultado_provisorio"
    if any(k in lower for k in ["retificacao", "retificação", "prorrogacao", "prorrogação"]):
        return "retificacao"
    return classify_document(title, link)


def classify_fal_edital(titulo: str, url: str = "", texto: str = "") -> Dict[str, str]:
    """Determina tipo, tipo_edital, programa e indicador de fluxo contínuo de um item da FAL."""
    title_and_url = f"{titulo} {url}".lower()
    combined = f"{titulo} {url} {texto}".lower()
    area = detect_fal_area(titulo, texto)

    if "cadastros-de-projetos" in title_and_url or "cadastro de projetos" in title_and_url:
        return {
            "tipo": "Submissão e Cadastro de Projetos de Campo",
            "tipo_edital": "Fluxo Contínuo / Cadastro de Projetos na FAL",
            "programa": "Submissão de Projetos de Ensino, Pesquisa e Extensão (FAL/SEI)",
            "area": area,
            "fluxo_continuo": "sim",
        }

    if (
        "fav.unb.br/estagio" in title_and_url
        or any(
            k in title_and_url
            for k in [
                "laboratório de",
                "laboratorio de",
                "centro de aquicultura",
                "centro de manejo",
                "viveiro florestal",
                "equipe de pesquisa em reprodução",
                "equipe de pesquisa em reproducao",
                "observatório astronômico",
                "observatorio astronomico",
                "estágio obrigatório",
                "estagio obrigatorio",
            ]
        )
    ):
        return {
            "tipo": "Estágio e Prática Profissional em Campo",
            "tipo_edital": "Prática de Campo / Estágio e Laboratórios Experimentais",
            "programa": "Estágios e Treinamento Técnico em Campo (FAL/FAV)",
            "area": area,
            "fluxo_continuo": "sim",
        }

    if any(
        k in combined
        for k in [
            "extensão",
            "extensao",
            "feira do produtor",
            "dia de campo",
            "semana do cavalo",
            "simpósio",
            "simposio",
            "ciclo de palestras",
            "beija fal",
            "beija-fal",
            "peixinho",
            "envelhecimento ativo",
            "soltura de papagaios",
            "incêndios florestais",
            "incendios florestais",
        ]
    ):
        return {
            "tipo": "Extensão Rural e Educação Ambiental",
            "tipo_edital": "Extensão Universitária / Eventos Rurais e Educação Ambiental",
            "programa": "Extensão Rural e Meio Ambiente (FAL/UnB)",
            "area": area,
            "fluxo_continuo": "nao",
        }

    if any(
        k in title_and_url
        for k in ["mobilidade", "intercâmbio", "intercambio", "fav/marca", "marca", "monitoria"]
    ):
        return {
            "tipo": "Ensino e Mobilidade Acadêmica em Ciências Agrárias",
            "tipo_edital": "Graduação / Mobilidade e Ensino em Ciências Agrárias (FAV/FAL)",
            "programa": "Ensino e Mobilidade Acadêmica (FAV/FAL UnB)",
            "area": area,
            "fluxo_continuo": "nao",
        }

    return {
        "tipo": "Pesquisa Aplicada e Pós-Graduação no Campo",
        "tipo_edital": "Pesquisa Científica / Agropecuária, Florestal e Ambiental",
        "programa": "Pesquisa Científica e Pós-Graduação na FAL/UnB",
        "area": area,
        "fluxo_continuo": "nao",
    }


def parse_fal_blog_listing_html(
    html: str,
    base_url: str = FAL_BASE_URL,
) -> List[Dict[str, str]]:
    """Extrai os artigos elegíveis (título, link, data e intro_html do card) de uma página de blog da FAL."""
    soup = BeautifulSoup(html or "", "html.parser")
    blog = soup.find("div", class_=lambda c: c and "blog" in c.split()) or soup
    entries: List[Dict[str, str]] = []
    seen_links = set()
    current_header_date = ""

    for heading in blog.find_all(["h2", "h3"]):
        a_tag = heading.find("a", href=True)
        heading_text = sanitize_fal_text(heading.get_text(" ", strip=True))
        if not a_tag:
            m_pt = DATE_PT_PATTERN.search(heading_text)
            if m_pt:
                current_header_date = m_pt.group(1)
            continue

        raw_href = str(a_tag["href"]).strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
            continue

        full_url = urljoin(base_url, raw_href)
        if full_url in seen_links:
            continue

        if is_fal_static_institutional(heading_text, full_url):
            continue

        card_node = heading.find_parent(
            "div",
            class_=lambda c: isinstance(c, str) and (c == "item" or c.startswith("leading-") or c.startswith("column-") or c == "items-row"),
        )
        intro_html = str(card_node) if card_node is not None else ""
        card_text = sanitize_fal_text(card_node.get_text(" ", strip=True)) if card_node is not None else ""
        m_iso = DATE_ISO_PATTERN.search(card_text)
        effective_date = m_iso.group(0) if m_iso else current_header_date

        seen_links.add(full_url)
        entries.append({
            "titulo": heading_text,
            "link": full_url,
            "header_date": effective_date,
            "intro_html": intro_html,
        })

    return entries


def _enrich_generic_fal_title(raw_title: str, combined_text: str, paragraphs: List[str], page_url: str) -> str:
    """Enriquece títulos genéricos (ex: 'Doutorado', 'Iniciação científica', 'Extensão') com o tema do projeto."""
    clean_title = sanitize_fal_text(raw_title)
    if clean_title.lower() not in GENERIC_ACADEMIC_TITLES:
        if not any(k in clean_title.lower() for k in ("fal", "fav", "fazenda água limpa", "fazenda agua limpa")):
            return f"{clean_title} — FAL/UnB"
        return clean_title

    # 1. Prioriza campo estruturado "Título: <nome do projeto>" presente nos cards do Joomla da FAL
    m_proj = EXPLICIT_PROJECT_TITLE_PATTERN.search(combined_text)
    if m_proj:
        proj_name = m_proj.group(1).strip(" -–:;.!")
        if len(proj_name) > 140:
            proj_name = proj_name[:135].rsplit(" ", 1)[0] + "..."
        if proj_name:
            return f"{clean_title} na FAL/UnB — {proj_name}"

    # 2. Fallback para a primeira sentença informativa dos parágrafos
    for p in paragraphs:
        candidate = re.sub(
            r"^(?:t[íi]tulo(?:\s+do\s+projeto)?|projeto|tema)\s*[:\-–]\s*",
            "",
            p,
            flags=re.IGNORECASE,
        ).strip()
        first_sentence = re.split(r"(?<=[.!?])\s+", candidate)[0].strip(" -–:;.!")
        if 12 <= len(first_sentence) <= 135:
            return f"{clean_title} na FAL/UnB — {first_sentence}"
        if len(first_sentence) > 135:
            truncated = first_sentence[:130].rsplit(" ", 1)[0]
            return f"{clean_title} na FAL/UnB — {truncated}..."

    m_slug = re.search(r"[?&]id=\d+:([a-z0-9-]+)", page_url.lower())
    slug_hint = m_slug.group(1).replace("-", " ").title() if m_slug else "Pesquisa de Campo"
    return f"{clean_title} na FAL/UnB ({slug_hint})"


def parse_fal_article_html(
    html: str,
    page_url: str,
    default_title: str = "",
    header_date: str = "",
    intro_html: str = "",
) -> Dict[str, Any]:
    """Extrai descrição higienizada, documentos, links de inscrição e categorias de um artigo da FAL/FAV."""
    soup = BeautifulSoup(html or "", "html.parser")
    for chrome in soup.select("header, footer, nav"):
        chrome.decompose()

    article_body = soup.find("div", itemprop="articleBody")
    container = (
        article_body
        or soup.find("div", class_="item-page")
        or soup.find("div", class_="entry-content")
        or soup.find("div", attrs={"data-elementor-type": "wp-page"})
        or soup.find("main")
        or soup
    )

    intro_soup = BeautifulSoup(intro_html or "", "html.parser") if intro_html else None
    extra_fallback = [soup] if article_body is None and container is not soup else []
    search_roots = [r for r in (intro_soup, container, *extra_fallback) if r is not None]

    h_el = (
        soup.find("div", class_="page-header")
        or container.find(["h1", "h2"])
        or soup.find(["h1", "h2"])
    )
    extracted_title = sanitize_fal_text(h_el.get_text(" ", strip=True)) if h_el else ""
    base_title = default_title or extracted_title or "Oportunidade de Campo FAL/UnB"

    # Extração de parágrafos limpos (sem spam), combinando introtext do card e corpo completo do artigo
    paragraphs: List[str] = []
    combined_raw_chunks: List[str] = []
    for root in search_roots:
        raw_root_txt = sanitize_fal_text(root.get_text(" ", strip=True))
        if raw_root_txt:
            combined_raw_chunks.append(raw_root_txt)
        for p in root.find_all(["p", "li"]):
            txt = sanitize_fal_text(p.get_text(" ", strip=True))
            if len(txt) < 25:
                continue
            if txt.lower() == base_title.lower():
                continue
            if txt not in paragraphs:
                paragraphs.append(txt)

    combined_text = " ".join(combined_raw_chunks).strip()
    if not paragraphs and combined_text:
        paragraphs.append(combined_text[:450])

    titulo = _enrich_generic_fal_title(base_title, combined_text, paragraphs, page_url)

    # Extração de documentos (.pdf, .docx, etc.) e links de inscrição (SIGAA, SEI, Forms)
    documentos: List[Dict[str, Any]] = []
    seen_docs = set()
    link_inscricao = ""

    for root in search_roots:
        for a in root.find_all("a", href=True):
            raw_href = str(a["href"]).strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
                continue

            link_text = sanitize_fal_text(a.get_text(" ", strip=True))
            if SPAM_KEYWORDS_PATTERN.search(f"{link_text} {raw_href}"):
                continue

            full_link = urljoin(page_url, raw_href)
            parsed_url = urlparse(full_link)
            if parsed_url.scheme.lower() not in ("http", "https"):
                continue

            lower_link = full_link.lower()
            parsed_host = parsed_url.netloc.lower()

            # Ignora domínios externos suspeitos sem vínculo acadêmico/governamental
            if parsed_host and not any(
                trusted in parsed_host
                for trusted in ("unb.br", "gov.br", "forms.gle", "forms.office.com", "docs.google.com", "youtube.com")
            ):
                continue

            if any(gen in lower_link for gen in GENERIC_SITE_FOOTER_DOCS):
                continue

            if any(
                k in lower_link
                for k in (
                    "sigaa.unb.br",
                    "sei.unb.br",
                    "inscricoes.unb.br",
                    "forms.gle",
                    "forms.office.com",
                    "docs.google.com/forms",
                )
            ):
                if not link_inscricao:
                    link_inscricao = full_link
            elif not link_inscricao and any(
                k in lower_link
                for k in ("saudeanimal.unb.br", "posagronomia.unb.br", "agronegocios.unb.br")
            ):
                link_inscricao = full_link

            if is_fal_document_url(full_link):
                if full_link not in seen_docs:
                    seen_docs.add(full_link)
                    doc_title = _clean_fal_doc_title(link_text, full_link)
                    documentos.append({
                        "titulo": doc_title,
                        "link": full_link,
                        "tipo": classify_fal_document(doc_title, full_link),
                    })

    # Data de publicação e ano
    full_text = " ".join(paragraphs) or combined_text
    raw_date = header_date
    if not raw_date:
        m_d = DATE_ISO_PATTERN.search(full_text) or DATE_SLASH_PATTERN.search(full_text) or DATE_PT_PATTERN.search(full_text)
        if m_d:
            raw_date = m_d.group(0)

    cat_info = classify_fal_edital(titulo, url=page_url, texto=full_text)
    is_continuous = cat_info["fluxo_continuo"] == "sim"

    m_yr = (
        GENERAL_YEAR_PATTERN.search(raw_date)
        or GENERAL_YEAR_PATTERN.search(titulo)
        or GENERAL_YEAR_PATTERN.search(full_text)
    )
    if m_yr:
        ano = int(m_yr.group(1))
    else:
        ano = 2026

    data_publicacao = _normalize_date_str(raw_date, default_year=ano)
    status = "aberto" if (is_continuous or ano >= 2025) else "fechado"

    descricao = (
        " ".join(paragraphs[:2]).strip()
        or f"Oportunidade acadêmica e prática de campo na Fazenda Água Limpa (FAL/UnB) em {cat_info['area']}: {titulo}."
    )
    assunto = f"Fazenda Água Limpa (FAL/UnB) — {cat_info['area']} ({cat_info['programa']}): {titulo}"

    return {
        "titulo": titulo,
        "assunto": assunto,
        "tipo": cat_info["tipo"],
        "tipo_edital": cat_info["tipo_edital"],
        "programa": cat_info["programa"],
        "area": cat_info["area"],
        "descricao": descricao,
        "resumo": descricao,
        "unidade": "FAL",
        "campus": "Fazenda Água Limpa",
        "link": page_url,
        "link_inscricao": link_inscricao,
        "data_publicacao": data_publicacao,
        "status": status,
        "ano": ano,
        "documentos": documentos,
    }


def parse_fav_wp_edital_post(post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Converte um post da API WordPress da FAV/FAL em item de edital caso seja chamada/seleção oficial."""
    if not isinstance(post, dict):
        return None

    link = str(post.get("link") or "").strip()
    if not link:
        return None

    title_obj = post.get("title")
    raw_title_html = str(title_obj.get("rendered") or "") if isinstance(title_obj, dict) else ""
    raw_title = sanitize_fal_text(BeautifulSoup(raw_title_html, "html.parser").get_text(" ", strip=True))

    content_obj = post.get("content")
    content_html = str(content_obj.get("rendered") or "") if isinstance(content_obj, dict) else ""
    raw_date = str(post.get("date") or "")[:10]

    low_title = raw_title.lower()
    has_edital_in_title = any(
        k in low_title for k in ("edital", "chamada", "processo seletivo", "seleção", "selecao")
    )

    content_soup = BeautifulSoup(content_html, "html.parser")
    edital_doc_label = ""
    has_edital_pdf = False
    for a in content_soup.find_all("a", href=True):
        href = urljoin(link, str(a["href"]).strip())
        txt = sanitize_fal_text(a.get_text(" ", strip=True))
        if is_fal_document_url(href) and any(
            k in f"{txt} {href}".lower() for k in ("edital", "chamada", "selecao", "seleção")
        ):
            has_edital_pdf = True
            if txt and txt.lower() not in {"clique aqui", "acesse aqui", "acesse aqui o edital"}:
                edital_doc_label = txt
                break

    if not has_edital_in_title and not has_edital_pdf:
        return None

    is_generic_post_title = low_title in {
        "acesse aqui o edital",
        "acesse o edital",
        "edital",
        "edital publicado",
    } or (len(raw_title) < 22 and not re.search(r"\d", raw_title))

    if is_generic_post_title and edital_doc_label:
        effective_title = f"{edital_doc_label} — FAV/FAL UnB"
    elif raw_title and not any(k in low_title for k in ("fal", "fav", "fazenda água limpa")):
        effective_title = f"{raw_title} — FAV/FAL UnB"
    else:
        effective_title = raw_title or "Edital FAV/FAL UnB"

    return parse_fal_article_html(
        f"<div class='entry-content'>{content_html}</div>",
        link,
        default_title=effective_title,
        header_date=raw_date,
    )


class FALScraper(BaseScraper):
    """Implementação do scraper para a Fazenda Água Limpa da UnB (FAL/UnB)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do órgão."""
        return "FAL"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Coleta oportunidades de estágio, práticas de campo, extensão e pesquisa da FAL/UnB.

        Args:
            year: Filtro opcional de ano de referência (ex: 2026, 2025).
            max_pages: Limite opcional de páginas do portal da FAL a percorrer.

        Returns:
            Lista de dicionários padronizados de oportunidades/chamadas da FAL.
        """
        editais: List[Dict[str, Any]] = []
        seen_links = set()
        seen_norm_titles = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                blog_entries: List[Dict[str, str]] = []
                seen_entry_urls = set()

                # 1. Percorre a paginação do portal oficial fal.unb.br (limitstart=0, 10, 20, ...)
                page_idx = 0
                max_offset = 60
                while page_idx * 10 <= max_offset:
                    if max_pages is not None and page_idx >= max_pages:
                        break
                    offset = page_idx * 10
                    list_url = f"{FAL_BLOG_URL}&limitstart={offset}"
                    try:
                        resp = client.get(list_url)
                        if resp.status_code != 200:
                            break
                        page_items = parse_fal_blog_listing_html(resp.text, base_url=str(resp.url))
                        if not page_items and offset > 0:
                            break
                        new_count = 0
                        for entry in page_items:
                            if entry["link"] not in seen_entry_urls:
                                seen_entry_urls.add(entry["link"])
                                blog_entries.append(entry)
                                new_count += 1
                        if offset > 0 and new_count == 0:
                            break
                    except httpx.HTTPError as exc:
                        logger.warning(f"Falha ao consultar listagem da FAL (limitstart={offset}): {exc}")
                        break
                    page_idx += 1

                # 2. Busca o conteúdo completo de cada oportunidade/projeto elegível da FAL
                def _fetch_article(entry: Dict[str, str]) -> Optional[Dict[str, Any]]:
                    try:
                        r = client.get(entry["link"])
                        article_html = r.text if r.status_code == 200 else ""
                        final_url = str(r.url) if r.status_code == 200 else entry["link"]
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao ler artigo da FAL ({entry['link']}): {exc}")
                        article_html = ""
                        final_url = entry["link"]

                    if not article_html and not entry.get("intro_html"):
                        return None

                    return parse_fal_article_html(
                        article_html,
                        final_url,
                        default_title=entry["titulo"],
                        header_date=entry["header_date"],
                        intro_html=entry.get("intro_html", ""),
                    )

                with ThreadPoolExecutor(max_workers=4) as pool:
                    article_items = list(pool.map(_fetch_article, blog_entries))

                for item in article_items:
                    if not item:
                        continue
                    self._url_to_docs_cache[item["link"]] = item.get("documentos", [])

                    # Remove duplicatas históricas idênticas (ex: mesmo projeto publicado 2 vezes em anos distintos)
                    norm_title_key = re.sub(r"[^a-z0-9]+", "", item["titulo"].lower())
                    if item["link"] in seen_links or norm_title_key in seen_norm_titles:
                        continue

                    if year is not None and item.get("ano") != year:
                        continue

                    seen_links.add(item["link"])
                    seen_norm_titles.add(norm_title_key)
                    editais.append(item)

                # 3. Inclui a página oficial de Estágio Obrigatório e Não Obrigatório FAV/FAL (com regulamento PDF)
                if FAV_ESTAGIO_URL not in seen_links:
                    try:
                        fav_resp = client.get(FAV_ESTAGIO_URL)
                        if fav_resp.status_code == 200:
                            fav_item = parse_fal_article_html(
                                fav_resp.text,
                                str(fav_resp.url),
                                default_title=(
                                    "Estágio Obrigatório e Não Obrigatório em Campo (FAV/FAL) — "
                                    "Agronomia, Medicina Veterinária e Agronegócios"
                                ),
                                header_date="01/01/2026",
                            )
                            self._url_to_docs_cache[fav_item["link"]] = fav_item.get("documentos", [])
                            if year is None or fav_item.get("ano") == year:
                                seen_links.add(fav_item["link"])
                                editais.append(fav_item)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Falha ao consultar página de estágios FAV/FAL: {exc}")

                # 4. Inclui editais ativos publicados no portal FAV/FAL (Agronomia, Veterinária, Saúde Animal, MARCA)
                try:
                    fav_api_resp = client.get(FAV_EDITAIS_API_URL)
                    if fav_api_resp.status_code == 200:
                        posts_payload = fav_api_resp.json()
                        if isinstance(posts_payload, list):
                            for post_obj in posts_payload:
                                fav_edital = parse_fav_wp_edital_post(post_obj)
                                if not fav_edital:
                                    continue
                                self._url_to_docs_cache[fav_edital["link"]] = fav_edital.get("documentos", [])
                                norm_key = re.sub(r"[^a-z0-9]+", "", fav_edital["titulo"].lower())
                                if fav_edital["link"] in seen_links or norm_key in seen_norm_titles:
                                    continue
                                if year is not None and fav_edital.get("ano") != year:
                                    continue
                                seen_links.add(fav_edital["link"])
                                seen_norm_titles.add(norm_key)
                                editais.append(fav_edital)
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    logger.warning(f"Falha ao consultar API de editais FAV/FAL: {exc}")

        except Exception as exc:
            logger.error(f"Erro geral no scraper da FAL: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos anexos (.pdf, .docx, etc.) de uma página de oportunidade da FAL/FAV."""
        if not edital_url:
            return []

        if edital_url in self._url_to_docs_cache:
            return self._url_to_docs_cache[edital_url]

        if is_fal_document_url(edital_url):
            return [{
                "titulo": _clean_fal_doc_title("", edital_url),
                "link": edital_url,
                "tipo": classify_fal_document(edital_url, edital_url),
            }]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code == 200:
                    parsed = parse_fal_article_html(resp.text, str(resp.url))
                    docs = parsed.get("documentos", [])
                    self._url_to_docs_cache[edital_url] = docs
                    return docs
        except Exception as exc:
            logger.warning(f"Erro ao extrair documentos da FAL em {edital_url}: {exc}")

        return []


fal_scraper = FALScraper()
