"""Scraper para processos seletivos e vestibulares da UnB realizados pelo Cebraspe."""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

CEBRASPE_BASE_URL = "https://www.cebraspe.org.br"
CEBRASPE_API_BASE = "https://apis.cebraspe.org.br/cebraspe/eventos"
CEBRASPE_API_VESTIBULARES = f"{CEBRASPE_API_BASE}/tipo/vestibulares/"
CEBRASPE_API_CONCURSOS = f"{CEBRASPE_API_BASE}/tipo/concursos/"
CEBRASPE_CDN_URL = "https://cdn.cebraspe.org.br/"

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Palavras-chave positivas para identificar vestibulares e processos seletivos da UnB no Cebraspe
UNB_KEYWORDS = [
    "unb",
    "vestunb",
    "pas",
    "educampo",
    "dcs_",
    "trfac_",
    "acessoenem",
    "cursos_he",
    "he_unb",
    "uab_15_licenciatura",
    "vestdist",
]

# Órgãos externos a serem descartados caso não contenham menção explícita à UnB
EXTERNAL_KEYWORDS = [
    "ufac",
    "uncisal",
    "uerr",
    "uesb",
    "unifal",
    "ufv",
]


def is_unb_event(event: Dict[str, Any]) -> bool:
    """Verifica se um evento do Cebraspe pertence à Universidade de Brasília (UnB).

    Args:
        event: Dicionário contendo dados do evento do Cebraspe.

    Returns:
        True se for processo seletivo da UnB, False caso contrário.
    """
    nome_abrev = str(event.get("eventoNomeAbreviado") or "").lower()
    nome_comp = str(event.get("eventoNomeCompleto") or "").lower()
    url_slug = str(event.get("eventoURL") or "").lower()
    full_text = f"{nome_abrev} {nome_comp} {url_slug}"

    # Se for de outra universidade sem menção à UnB, descarta
    if any(ext in full_text for ext in EXTERNAL_KEYWORDS) and "unb" not in full_text:
        return False

    return any(k in full_text for k in UNB_KEYWORDS)


def build_cebraspe_document_url(arquivo_info: Dict[str, Any], identificador: str, tipo_evento: str = "vestibulares") -> str:
    """Constrói a URL canônica de download de um arquivo no CDN do Cebraspe.

    Reproduz fielmente a lógica de renderização do componente oficial do Cebraspe.
    """
    nome = arquivo_info.get("nomeArquivo", "").strip()
    is_guid = arquivo_info.get("isGuid", False)
    tipo_ext = arquivo_info.get("tipoExtensaoArquivo", "")

    if not nome:
        return ""

    if is_guid:
        return f"{CEBRASPE_CDN_URL}{nome}"

    if tipo_ext == "_explorer":
        if tipo_evento == "vestibulares":
            return f"http://www.cespe.unb.br/vestibular/{identificador}/arquivos/{nome}"
        return f"http://www.cespe.unb.br/{tipo_evento}/{identificador}/arquivos/{nome}"

    if tipo_evento == "vestibulares":
        return f"{CEBRASPE_CDN_URL}vestibulares/{identificador}/arquivos/{nome}"
    return f"{CEBRASPE_CDN_URL}{tipo_evento}/{identificador}/arquivos/{nome}"


class CebraspeScraper(BaseScraper):
    """Implementação do scraper para processos seletivos da UnB via API oficial do Cebraspe."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._identificador_cache: Dict[str, Dict[str, Any]] = {}
        self._url_to_id_cache: Dict[str, str] = {}

    @property
    def orgao_origem(self) -> str:
        return "CEBRASPE"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Consulta os processos seletivos e vestibulares da UnB via API do Cebraspe."""
        editais: List[Dict[str, Any]] = []
        seen_identificadores = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # Consulta vestibulares e processos seletivos
                endpoints = [CEBRASPE_API_VESTIBULARES, CEBRASPE_API_CONCURSOS]
                for endpoint in endpoints:
                    try:
                        resp = client.get(endpoint)
                        if resp.status_code != 200:
                            continue
                        fases = resp.json()
                    except (httpx.HTTPError, ValueError) as exc:
                        logger.warning(f"Erro ao consultar endpoint {endpoint} do Cebraspe: {exc}")
                        continue

                    if not isinstance(fases, list):
                        continue

                    for fase in fases:
                        fase_nome = fase.get("faseEvento") or "Em Andamento"
                        eventos = fase.get("eventos", []) or []

                        for ev in eventos:
                            if not is_unb_event(ev):
                                continue

                            identificador = ev.get("eventoURL") or ""
                            if not identificador or identificador in seen_identificadores:
                                continue
                            seen_identificadores.add(identificador)

                            # Extração de ano
                            ano_ev: Optional[int] = None
                            raw_ano = ev.get("eventoAno")
                            if raw_ano and str(raw_ano).isdigit():
                                ano_ev = int(raw_ano)
                            elif len(identificador) >= 2:
                                # Tenta extrair ano de slugs como VESTUNB_26 ou UNB_26_2_TF_DCS
                                match = re.search(r"(\d{2})", identificador)
                                if match:
                                    ano_val = int(match.group(1))
                                    ano_ev = 2000 + ano_val if ano_val < 50 else 1900 + ano_val

                            if year is not None and ano_ev is not None and ano_ev != year:
                                continue

                            titulo = ev.get("eventoNomeCompleto") or ev.get("eventoNomeAbreviado") or f"Processo Seletivo UnB {identificador}"
                            url_evento = f"{CEBRASPE_BASE_URL}/concursos/{identificador}"

                            # Mapeamento de status
                            status_normalizado = "aberto" if fase_nome.lower() in ["novos", "inscrições abertas", "inscricoes abertas", "em andamento"] else "fechado"

                            is_vest = "vestibulares" in endpoint
                            ev_tipo = "Vestibular" if is_vest else "Concurso Público"
                            ev_assunto = f"Vestibular / Acesso Superior UnB - {titulo}" if is_vest else f"Concurso Público UnB - {titulo}"
                            ev_desc = f"Processo seletivo / vestibular organizado pelo Cebraspe para a Universidade de Brasília ({titulo}). Vagas: {ev.get('eventoTotalVagas', 'Conforme edital')}."

                            edital_dict: Dict[str, Any] = {
                                "titulo": titulo,
                                "assunto": ev_assunto,
                                "tipo": ev_tipo,
                                "tipo_edital": f"{ev_tipo} / Cebraspe",
                                "descricao": ev_desc,
                                "resumo": ev_desc,
                                "link": url_evento,
                                "identificador": identificador,
                                "fase": fase_nome,
                                "status": status_normalizado,
                                "vagas": ev.get("eventoTotalVagas"),
                                "ano": ano_ev,
                                "tipo_evento": "vestibulares" if is_vest else "concursos",
                                "data_publicacao": f"{ano_ev}-01-01" if ano_ev else "",
                            }

                            self._identificador_cache[identificador] = edital_dict
                            self._url_to_id_cache[url_evento] = identificador
                            editais.append(edital_dict)

        except Exception as exc:
            logger.error(f"Erro geral ao consultar Cebraspe: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai os editais de abertura, retificações e resultados em PDF de um evento do Cebraspe."""
        documentos: List[Dict[str, Any]] = []

        identificador = self._url_to_id_cache.get(edital_url)
        if not identificador:
            # Tenta extrair do final do path da URL
            path_parts = urlparse(edital_url).path.strip("/").split("/")
            if path_parts:
                identificador = path_parts[-1]

        if not identificador:
            return documentos

        detail_url = f"{CEBRASPE_API_BASE}/{identificador}"

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(detail_url)
                if resp.status_code != 200:
                    return documentos

                data = resp.json()
                tipo_evento = data.get("eventoTipo") or "vestibulares"
                arquivos = data.get("arquivosEdital") or []

                seen_links = set()
                for arq in arquivos:
                    nome = arq.get("nomeArquivo", "")
                    if not nome:
                        continue

                    # Aceita PDFs e links com extensão de documento
                    pdf_url = build_cebraspe_document_url(arq, identificador, tipo_evento=tipo_evento)
                    if not pdf_url or pdf_url in seen_links:
                        continue
                    seen_links.add(pdf_url)

                    desc = arq.get("descricaoArquivo") or nome
                    documentos.append({
                        "titulo": desc,
                        "link": pdf_url,
                        "tipo": classify_document(desc, pdf_url),
                        "data_publicacao": arq.get("dataArquivoObj") or arq.get("dataArquivo") or "",
                    })

        except Exception as exc:
            logger.error(f"Erro ao buscar documentos para {identificador} no Cebraspe: {exc}")

        return documentos


cebraspe_scraper = CebraspeScraper()
