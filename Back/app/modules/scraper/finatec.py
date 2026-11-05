"""Scraper para a FINATEC (Fundação de Empreendimentos Científicos e Tecnológicos).

Coleta editais de bolsas em projetos de Pesquisa e Desenvolvimento (P&D),
seleção de pesquisadores/consultores celetistas, estagiários de projetos e
chamadas públicas de fomento à inovação vinculadas à UnB.

Fontes oficiais:
- API REST WordPress de Editais/Vagas de Projetos: https://www.finatec.org.br/wp-json/wp/v2/vaga
- API REST WordPress de Editais e Oportunidades: https://www.finatec.org.br/wp-json/wp/v2/posts?categories=16,15,9
- Portal HTML de Editais: https://www.finatec.org.br/editais/
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

FINATEC_BASE_URL = "https://www.finatec.org.br"
FINATEC_VAGAS_API_URL = f"{FINATEC_BASE_URL}/wp-json/wp/v2/vaga"
FINATEC_POSTS_API_URL = f"{FINATEC_BASE_URL}/wp-json/wp/v2/posts"
FINATEC_EDITAIS_HTML_URL = f"{FINATEC_BASE_URL}/editais/"

# IDs das categorias no WordPress da Finatec:
# 16 = editais, 15 = editais-prospecta-ampla-divulgacao, 9 = oportunidades
FINATEC_EDITAIS_CATEGORY_IDS = "16,15,9"

DEFAULT_TIMEOUT = 20.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fique-de-Olho/1.0"

EDITAL_YEAR_PATTERN = re.compile(r"\b\d{1,4}/(20\d{2})\b")
GENERAL_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _clean_html_text(raw: str) -> str:
    """Remove tags HTML, decodifica entidades e normaliza espaços."""
    if not raw:
        return ""
    unescaped = html_lib.unescape(raw)
    if "<" in unescaped and ">" in unescaped:
        text = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
    else:
        text = unescaped
    return re.sub(r"\s+", " ", text).strip()


def classify_finatec_document(title: str, link: str) -> str:
    """Classifica um documento anexo da Finatec conforme o padrão do projeto."""
    lower = f"{title} {link}".lower()
    if any(k in lower for k in ["resultado final", "resultado_final", "resultado-final", "homologacao", "homologação"]):
        return "resultado_final"
    if any(k in lower for k in ["resultado preliminar", "resultado_preliminar", "resultado-preliminar", "resultado provisorio", "resultado provisório", "resultado etapa"]):
        return "resultado_provisorio"
    if any(k in lower for k in ["retificacao", "retificação", "alteracao de cronograma", "alteração de cronograma", "alteracao de horario", "prorrogacao", "prorrogação"]):
        return "retificacao"
    return classify_document(title, link)


def classify_finatec_edital(titulo: str, class_list: Optional[List[str]] = None) -> Dict[str, Any]:
    """Determina o tipo, subtipo, modalidade, locais e áreas de atuação de um edital da Finatec."""
    class_list = class_list or []
    lower_title = titulo.lower()
    classes_joined = " ".join(class_list).lower()

    areas: List[str] = []
    locais: List[str] = []
    for cls in class_list:
        if cls.startswith("area_de_atuacao-"):
            slug_area = cls.replace("area_de_atuacao-", "").replace("-", " ").title()
            if slug_area not in areas:
                areas.append(slug_area)
        elif cls.startswith("local-"):
            slug_local = cls.replace("local-", "").replace("-", " ").title()
            if slug_local not in locais:
                locais.append(slug_local)

    if "contratacao-edital-bolsista" in classes_joined or any(k in lower_title for k in ["bolsista", "bolsa"]):
        tipo = "Bolsas de Pesquisa e P&D"
        tipo_edital = "Pesquisa e Inovação / Bolsa de Projeto"
        modalidade = "Edital de Bolsista"
    elif "contratacao-edital-estagiario" in classes_joined or any(k in lower_title for k in ["estagiário", "estagiario", "estágio", "estagio"]):
        tipo = "Estágio em Projeto"
        tipo_edital = "Estágio / Projeto Finatec"
        modalidade = "Edital de Estagiário"
    elif "contratacao-edital-celetista" in classes_joined or "celetista" in classes_joined or "celetista" in lower_title:
        tipo = "Seleção de Pesquisador / Celetista"
        tipo_edital = "Pesquisa e Desenvolvimento / Celetista de Projeto"
        modalidade = "Edital de Celetista"
    else:
        tipo = "Fomento e Pesquisa (P&D)"
        tipo_edital = "Fomento e Inovação / Finatec"
        modalidade = "Chamada / Edital de Fomento"

    return {
        "tipo": tipo,
        "tipo_edital": tipo_edital,
        "modalidade": modalidade,
        "areas": areas,
        "locais": locais,
    }


def parse_finatec_content_html(content_html: str, base_url: str = FINATEC_BASE_URL) -> Dict[str, Any]:
    """Extrai documentos PDF, links de inscrição e texto descritivo do HTML de um edital da Finatec."""
    soup = BeautifulSoup(content_html or "", "html.parser")
    container = (
        soup.find("div", class_="entry-content")
        or soup.find("article")
        or soup.find("main")
        or soup
    )

    documentos: List[Dict[str, Any]] = []
    seen_links = set()
    has_final = False
    link_inscricao = ""

    for a in container.find_all("a", href=True):
        href = str(a["href"]).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        full_url = urljoin(base_url, href)
        text = _clean_html_text(a.get_text(" ", strip=True))
        lower_href = full_url.lower()
        lower_text = text.lower()

        if "editais_finatec" in lower_href or "inscreva" in lower_text or "inscrição" in lower_text or "inscricao" in lower_text:
            if not lower_href.endswith(".pdf"):
                link_inscricao = full_url
                continue

        is_doc = (
            lower_href.endswith((".pdf", ".doc", ".docx"))
            or "/wp-content/uploads/" in lower_href
        )
        if not is_doc:
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        doc_title = text or "Documento Oficial Finatec"
        doc_type = classify_finatec_document(doc_title, full_url)
        if doc_type == "resultado_final":
            has_final = True

        documentos.append({
            "titulo": doc_title,
            "link": full_url,
            "tipo": doc_type,
        })

    texto_limpo = _clean_html_text(container.get_text(" ", strip=True))
    return {
        "documentos": documentos,
        "has_final": has_final,
        "link_inscricao": link_inscricao,
        "texto_limpo": texto_limpo,
    }


def parse_finatec_wp_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Converte um item JSON da API REST WordPress da Finatec em dicionário padronizado de edital."""
    raw_title = (item.get("title") or {}).get("rendered") if isinstance(item.get("title"), dict) else str(item.get("title") or "")
    titulo = _clean_html_text(raw_title) or "Edital Finatec"
    link = str(item.get("link") or "").strip()

    date_raw = str(item.get("date") or "").strip()
    data_pub = date_raw[:10] if len(date_raw) >= 10 else ""

    # Determinação do ano do edital
    ano: Optional[int] = None
    m_edital_year = EDITAL_YEAR_PATTERN.search(titulo)
    if m_edital_year:
        ano = int(m_edital_year.group(1))
    elif data_pub and len(data_pub) >= 4 and data_pub[:4].isdigit():
        ano = int(data_pub[:4])
    else:
        m_gen_year = GENERAL_YEAR_PATTERN.search(titulo)
        if m_gen_year:
            ano = int(m_gen_year.group(1))

    class_list = item.get("class_list") if isinstance(item.get("class_list"), list) else []
    cat_info = classify_finatec_edital(titulo, class_list=class_list)

    content_html = (item.get("content") or {}).get("rendered") if isinstance(item.get("content"), dict) else str(item.get("content") or "")
    parsed_content = parse_finatec_content_html(content_html, base_url=link or FINATEC_BASE_URL)
    documentos = parsed_content["documentos"]
    has_final = parsed_content["has_final"]

    # Status: fechado se já possui Resultado Final ou se é de anos anteriores a 2026
    if has_final or (ano is not None and ano < 2026):
        status = "fechado"
    else:
        status = "aberto"

    areas_str = ", ".join(cat_info["areas"][:5])
    locais_str = ", ".join(cat_info["locais"])

    assunto = f"Seleção Finatec ({cat_info['tipo']}) - {titulo}"
    desc_parts = [f"Modalidade: {cat_info['modalidade']}"]
    if areas_str:
        desc_parts.append(f"Áreas de Atuação: {areas_str}")
    if locais_str:
        desc_parts.append(f"Local: {locais_str}")
    desc_parts.append(f"Processo seletivo / edital conduzido pela FINATEC (Fundação de Projetos da UnB): {titulo}.")
    descricao = " | ".join(desc_parts)

    return {
        "titulo": titulo,
        "assunto": assunto,
        "tipo": cat_info["tipo"],
        "tipo_edital": cat_info["tipo_edital"],
        "modalidade": cat_info["modalidade"],
        "descricao": descricao,
        "resumo": descricao,
        "unidade": "FINATEC",
        "areas": cat_info["areas"],
        "locais": cat_info["locais"],
        "link": link,
        "link_inscricao": parsed_content["link_inscricao"],
        "data_publicacao": data_pub,
        "status": status,
        "ano": ano,
        "documentos": documentos,
    }


def parse_finatec_editais_html(html: str, base_url: str = FINATEC_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai editais a partir da página HTML de arquivo /editais/ da Finatec."""
    soup = BeautifulSoup(html or "", "html.parser")
    main = soup.find("main") or soup
    editais: List[Dict[str, Any]] = []
    seen_links = set()

    articles = main.find_all("article")
    if not articles:
        # Fallback por cabeçalhos h2 dentro do main
        for h2 in main.find_all("h2"):
            a = h2.find("a", href=True)
            if not a:
                continue
            link = urljoin(base_url, str(a["href"]).strip())
            if link in seen_links:
                continue
            seen_links.add(link)
            titulo = _clean_html_text(a.get_text(" ", strip=True))
            if not titulo or "navegação" in titulo.lower():
                continue

            m_year = EDITAL_YEAR_PATTERN.search(titulo) or GENERAL_YEAR_PATTERN.search(titulo)
            ano = int(m_year.group(1)) if m_year else None
            cat_info = classify_finatec_edital(titulo)
            assunto = f"Seleção Finatec ({cat_info['tipo']}) - {titulo}"
            descricao = f"Edital publicado pela FINATEC (Fundação de Empreendimentos Científicos e Tecnológicos da UnB): {titulo}."

            editais.append({
                "titulo": titulo,
                "assunto": assunto,
                "tipo": cat_info["tipo"],
                "tipo_edital": cat_info["tipo_edital"],
                "descricao": descricao,
                "resumo": descricao,
                "unidade": "FINATEC",
                "link": link,
                "data_publicacao": f"{ano}-01-01" if ano else "",
                "status": "aberto" if (ano and ano >= 2026) else "fechado",
                "ano": ano,
                "documentos": [],
            })
        return editais

    for art in articles:
        h2 = art.find(["h2", "h3"])
        a = h2.find("a", href=True) if h2 else art.find("a", href=True)
        if not a:
            continue

        link = urljoin(base_url, str(a["href"]).strip())
        if link in seen_links:
            continue
        seen_links.add(link)

        titulo = _clean_html_text(a.get_text(" ", strip=True))
        if not titulo:
            continue

        time_el = art.find("time")
        data_pub = ""
        if time_el and time_el.get("datetime"):
            data_pub = str(time_el["datetime"])[:10]

        parsed_content = parse_finatec_content_html(str(art), base_url=link)
        m_year = EDITAL_YEAR_PATTERN.search(titulo) or GENERAL_YEAR_PATTERN.search(titulo)
        ano = int(m_year.group(1)) if m_year else (int(data_pub[:4]) if data_pub and data_pub[:4].isdigit() else None)

        cat_info = classify_finatec_edital(titulo, class_list=art.get("class", []))
        status = "fechado" if (parsed_content["has_final"] or (ano is not None and ano < 2026)) else "aberto"
        assunto = f"Seleção Finatec ({cat_info['tipo']}) - {titulo}"
        descricao = f"Edital publicado pela FINATEC (Fundação de Empreendimentos Científicos e Tecnológicos da UnB): {titulo}."

        editais.append({
            "titulo": titulo,
            "assunto": assunto,
            "tipo": cat_info["tipo"],
            "tipo_edital": cat_info["tipo_edital"],
            "descricao": descricao,
            "resumo": descricao,
            "unidade": "FINATEC",
            "link": link,
            "data_publicacao": data_pub,
            "status": status,
            "ano": ano,
            "documentos": parsed_content["documentos"],
        })

    return editais


class FinatecScraper(BaseScraper):
    """Implementação do scraper para a FINATEC (Fundação de Projetos da UnB)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do órgão."""
        return "FINATEC"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pages: Optional[int] = None,
        include_posts: bool = True,
    ) -> List[Dict[str, Any]]:
        """Coleta os editais de bolsas, pesquisadores celetistas, estágios e fomento da FINATEC.

        Args:
            year: Ano de referência para filtragem opcional (ex: 2026, 2025).
            max_pages: Limite máximo de páginas de 100 itens da API de vagas (None para todas).
            include_posts: Se verdadeiro, inclui também posts das categorias de editais/fomento.

        Returns:
            Lista de dicionários padronizados de editais da FINATEC.
        """
        editais: List[Dict[str, Any]] = []
        seen_links = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Coleta todos os editais do Custom Post Type 'vaga' (Bolsistas, Celetistas, Estagiários)
                page = 1
                total_pages = 1

                while page <= total_pages:
                    if max_pages is not None and page > max_pages:
                        break

                    try:
                        resp = client.get(
                            FINATEC_VAGAS_API_URL,
                            params={"per_page": 100, "page": page},
                        )
                        if resp.status_code != 200:
                            break
                        items = resp.json()
                        if not isinstance(items, list) or not items:
                            break
                        total_pages = int(resp.headers.get("x-wp-totalpages", 1))
                    except (httpx.HTTPError, ValueError) as exc:
                        logger.warning(f"Erro ao consultar página {page} da API de vagas da FINATEC: {exc}")
                        break

                    page_years: List[int] = []
                    for item in items:
                        edital = parse_finatec_wp_item(item)
                        if edital["link"]:
                            self._url_to_docs_cache[edital["link"]] = edital["documentos"]
                        if edital.get("ano"):
                            page_years.append(edital["ano"])

                        if year is not None and edital.get("ano") is not None and edital["ano"] != year:
                            continue

                        if edital["link"] and edital["link"] not in seen_links:
                            seen_links.add(edital["link"])
                            editais.append(edital)

                    # Otimização cronológica: se filtramos por ano e a página inteira já é mais antiga que (year - 1)
                    if year is not None and page_years and max(page_years) < year:
                        break

                    page += 1

                # 2. Coleta chamadas institucionais e editais de fomento em /wp-json/wp/v2/posts
                if include_posts:
                    try:
                        resp_posts = client.get(
                            FINATEC_POSTS_API_URL,
                            params={"categories": FINATEC_EDITAIS_CATEGORY_IDS, "per_page": 100},
                        )
                        if resp_posts.status_code == 200:
                            posts = resp_posts.json()
                            if isinstance(posts, list):
                                for post in posts:
                                    edital = parse_finatec_wp_item(post)
                                    if edital["link"]:
                                        self._url_to_docs_cache[edital["link"]] = edital["documentos"]

                                    if year is not None and edital.get("ano") is not None and edital["ano"] != year:
                                        continue

                                    if edital["link"] and edital["link"] not in seen_links:
                                        seen_links.add(edital["link"])
                                        editais.append(edital)
                    except (httpx.HTTPError, ValueError) as exc:
                        logger.warning(f"Erro ao consultar posts de editais da FINATEC: {exc}")

        except Exception as exc:
            logger.error(f"Erro geral no scraper da FINATEC: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos PDF vinculados a uma página de edital da FINATEC."""
        if not edital_url:
            return []

        if edital_url in self._url_to_docs_cache:
            return self._url_to_docs_cache[edital_url]

        if edital_url.lower().endswith(".pdf"):
            return [{
                "titulo": "Edital Oficial Finatec",
                "link": edital_url,
                "tipo": classify_finatec_document(edital_url, edital_url),
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
                    parsed = parse_finatec_content_html(resp.text, base_url=str(resp.url))
                    docs = parsed["documentos"]
                    self._url_to_docs_cache[edital_url] = docs
                    return docs
        except Exception as exc:
            logger.warning(f"Erro ao extrair documentos da FINATEC em {edital_url}: {exc}")

        return []


finatec_scraper = FinatecScraper()
