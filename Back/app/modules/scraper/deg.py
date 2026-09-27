import re
import unicodedata
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

DEG_BASE_URL = "https://deg.unb.br"
DEFAULT_TIMEOUT = 10.0
DATE_PATTERN = re.compile(
    r"\b\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{4}\b",
    re.IGNORECASE,
)
DOCUMENT_TYPES = (
    ("resultado_final", ("resultado_final", "resultado final")),
    ("resultado_provisorio", ("resultado_provisorio", "resultado provisorio")),
    ("retificacao", ("retificacao",)),
    ("homologacao", ("homologacao",)),
)


def build_editais_url(year: int | None = None) -> str:
    """Monta a URL da listagem atual ou de um ano específico do portal DEG."""
    if year is None:
        return f"{DEG_BASE_URL}/editais/"

    if year < 2000 or year > 2100:
        raise ValueError("O ano deve estar entre 2000 e 2100.")

    return f"{DEG_BASE_URL}/editais-{year}/"


def parse_editais(html: str, base_url: str = DEG_BASE_URL) -> list[dict[str, str]]:
    """Extrai título, link e data de publicação do HTML da listagem do DEG."""
    soup = BeautifulSoup(html, "html.parser")
    editais: list[dict[str, str]] = []

    for heading in soup.find_all("h6"):
        link_element = heading.find("a", href=True)
        if link_element is None:
            continue

        title = link_element.get_text(" ", strip=True)
        link = urljoin(base_url, str(link_element["href"]))
        date_match = DATE_PATTERN.search(heading.find_next(string=DATE_PATTERN) or "")

        editais.append(
            {
                "titulo": title,
                "link": link,
                "data_publicacao": date_match.group(0) if date_match else "",
            }
        )

    return editais


def fetch_editais(year: int | None = None, timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, str]]:
    """Busca a listagem do DEG e retorna uma lista vazia em falhas de rede."""
    try:
        response = httpx.get(
            build_editais_url(year),
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Fique-de-Olho/1.0"},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    return parse_editais(response.text)


def _normalize_document_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "_", without_accents.lower()).strip("_")


def classify_document(title: str, link: str) -> str:
    """Classifica um documento usando o texto do link e o nome do arquivo."""
    searchable_text = _normalize_document_text(f"{title} {link}")

    for document_type, keywords in DOCUMENT_TYPES:
        if any(_normalize_document_text(keyword) in searchable_text for keyword in keywords):
            return document_type

    return "original"


def parse_documentos(html: str, base_url: str = DEG_BASE_URL) -> list[dict[str, str]]:
    """Extrai PDFs vinculados ao conteúdo principal de uma página de edital."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".entry-content") or soup
    documentos: list[dict[str, str]] = []

    for link_element in content.select("a[href]"):
        href = str(link_element["href"])
        if ".pdf" not in href.lower():
            continue

        title = link_element.get_text(" ", strip=True)
        link = urljoin(base_url, href)
        documentos.append(
            {
                "titulo": title,
                "link": link,
                "tipo": classify_document(title, link),
            }
        )

    return documentos


def fetch_documentos(url: str, timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, str]]:
    """Busca uma página de edital e retorna seus PDFs classificados."""
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Fique-de-Olho/1.0"},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    return parse_documentos(response.text, base_url=url)


def edital_to_dict(edital: Any) -> dict[str, str]:
    """Mantém um ponto de conversão explícito para integrações futuras."""
    return {
        "titulo": str(edital["titulo"]),
        "link": str(edital["link"]),
        "data_publicacao": str(edital["data_publicacao"]),
    }