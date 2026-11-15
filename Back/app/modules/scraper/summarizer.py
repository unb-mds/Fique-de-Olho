"""Camada 2 — Orquestração híbrida (heurística + LLM) de títulos e resumos de editais.

Issues #77 (resumo automático) e #106 (normalização de títulos vagos/genéricos).

Fluxo:
1. Calcula sempre o resultado determinístico da Camada 1 (``parser.py``):
   ``reconstruir_titulo_edital`` e ``extrair_objeto_edital``.
2. Se ``GEMINI_API_KEY`` estiver configurada, houver conteúdo textual e o título
   for vago ou o resumo estiver ausente/genérico, faz **uma única** chamada à
   Google Gemini API (``generateContent``) via ``httpx``.
3. Graceful degradation: ausência de chave, erro HTTP, timeout, JSON inválido ou
   título ainda vago resultam em ``logger.warning`` e fallback transparente para a
   Camada 1 — nenhuma exceção é propagada ao pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.modules.scraper.parser import (
    MAX_RESUMO_CHARS,
    MAX_TITULO_CHARS,
    _norm_key,
    extrair_objeto_edital,
    is_vague_title,
    limpar_texto_documento,
    reconstruir_titulo_edital,
    truncar_texto,
    truncar_titulo,
)

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TEMPERATURE = 0.2
MAX_TITULO_LLM_CHARS = 110
MAX_TEXTO_PROMPT_CHARS = 6000
MIN_RESUMO_INFORMATIVO_CHARS = 25

_RESUMOS_GENERICOS_PREFIXOS: Tuple[str, ...] = (
    "edital publicado pelo portal",
    "edital publicado no portal",
    "sem resumo",
    "resumo nao disponivel",
)

_missing_key_warned = False


def is_generic_summary(resumo: Optional[str], titulo: Optional[str] = None) -> bool:
    """Indica se o resumo está ausente, é curto demais, genérico ou apenas repete o título."""
    if not resumo or not str(resumo).strip():
        return True
    clean = " ".join(str(resumo).split())
    if len(clean) < MIN_RESUMO_INFORMATIVO_CHARS:
        return True
    key = _norm_key(clean)
    if any(key.startswith(p) for p in _RESUMOS_GENERICOS_PREFIXOS):
        return True
    if titulo and key == _norm_key(titulo):
        return True
    return False


@dataclass(frozen=True)
class _Plano:
    """Resultado da Camada 1 e decisão sobre a chamada à Camada 2."""

    titulo_vago: bool
    titulo_heuristico: str
    resumo_heuristico: Optional[str]
    prompt: Optional[str]


def _build_client(timeout: float) -> httpx.Client:
    """Cria o cliente HTTP síncrono (ponto de extensão para mocks nos testes)."""
    return httpx.Client(timeout=timeout)


def _build_async_client(timeout: float) -> httpx.AsyncClient:
    """Cria o cliente HTTP assíncrono (ponto de extensão para mocks nos testes)."""
    return httpx.AsyncClient(timeout=timeout)


def _resumo_heuristico(
    titulo: str,
    texto_extraido: Optional[str],
    assunto: Optional[str],
    resumo_atual: Optional[str],
) -> Optional[str]:
    """Resumo da Camada 1: resumo atual informativo > objeto do PDF > assunto > resumo atual bruto."""
    if not is_generic_summary(resumo_atual, titulo):
        return truncar_texto(resumo_atual, MAX_RESUMO_CHARS)
    objeto = extrair_objeto_edital(texto_extraido)
    if objeto:
        return objeto
    if assunto and not is_generic_summary(assunto, titulo):
        return truncar_texto(assunto, MAX_RESUMO_CHARS)
    if resumo_atual and resumo_atual.strip() and _norm_key(resumo_atual) != _norm_key(titulo):
        return truncar_texto(resumo_atual, MAX_RESUMO_CHARS)
    return None


def _montar_prompt(
    titulo: str,
    pedir_titulo: bool,
    texto_extraido: Optional[str],
    assunto: Optional[str],
    orgao_emissor: Optional[str],
    url_pdf: Optional[str],
) -> str:
    if pedir_titulo:
        formato = '{"titulo": "...", "resumo": "..."}'
        regra_titulo = (
            f'- "titulo": título claro e padronizado em português, com no máximo {MAX_TITULO_LLM_CHARS} '
            "caracteres, incluindo o órgão emissor, o programa e/ou número do edital e a etapa "
            "(ex.: Resultado Final, Convocação, Retificação) quando aplicável. Nunca use termos vagos "
            "isolados como Edital, Aqui, Download ou siglas sozinhas.\n"
        )
    else:
        formato = '{"resumo": "..."}'
        regra_titulo = ""

    texto = truncar_texto(limpar_texto_documento(texto_extraido), MAX_TEXTO_PROMPT_CHARS) if texto_extraido else ""
    return (
        "Você organiza editais da Universidade de Brasília (UnB) para estudantes.\n"
        f"Responda SOMENTE com um objeto JSON válido no formato {formato}.\n"
        "Regras:\n"
        f"{regra_titulo}"
        f'- "resumo": no máximo 2 frases (até {MAX_RESUMO_CHARS} caracteres) explicando a oportunidade e o '
        "público-alvo para estudantes da UnB. Não invente informações que não estejam no conteúdo.\n\n"
        f"Título atual: {titulo or '(vazio)'}\n"
        f"Órgão emissor: {orgao_emissor or '(não informado)'}\n"
        f"Assunto: {assunto or '(não informado)'}\n"
        f"Link do PDF: {url_pdf or '(não informado)'}\n"
        f'Conteúdo do edital (trecho):\n"""\n{texto or "(indisponível)"}\n"""\n'
    )


def _planejar(
    titulo: Optional[str],
    texto_extraido: Optional[str],
    assunto: Optional[str],
    orgao_emissor: Optional[str],
    url_pdf: Optional[str],
    resumo_atual: Optional[str],
) -> _Plano:
    global _missing_key_warned

    titulo_str = (titulo or "").strip()
    titulo_vago = is_vague_title(titulo_str)
    titulo_heur = reconstruir_titulo_edital(titulo_str, texto_extraido, assunto, orgao_emissor, url_pdf)
    resumo_heur = _resumo_heuristico(titulo_str, texto_extraido, assunto, resumo_atual)

    tem_conteudo = bool((texto_extraido and texto_extraido.strip()) or (assunto and assunto.strip()))
    precisa_llm = tem_conteudo and (titulo_vago or is_generic_summary(resumo_atual, titulo_str))

    prompt: Optional[str] = None
    if precisa_llm:
        if not settings.GEMINI_API_KEY:
            if not _missing_key_warned:
                logger.warning(
                    "GEMINI_API_KEY não configurada; títulos/resumos usarão apenas a heurística local (Camada 1)."
                )
                _missing_key_warned = True
        else:
            prompt = _montar_prompt(titulo_str, titulo_vago, texto_extraido, assunto, orgao_emissor, url_pdf)

    return _Plano(
        titulo_vago=titulo_vago,
        titulo_heuristico=titulo_heur,
        resumo_heuristico=resumo_heur,
        prompt=prompt,
    )


def _request_args(prompt: str) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    url = GEMINI_ENDPOINT.format(model=settings.GEMINI_MODEL)
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"}
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "responseMimeType": "application/json",
        },
    }
    return url, headers, body


def _parse_resposta(response: httpx.Response) -> Dict[str, Any]:
    """Extrai o JSON gerado pelo modelo. Levanta exceção em qualquer formato inesperado."""
    response.raise_for_status()
    payload = response.json()
    parts = payload["candidates"][0]["content"]["parts"]
    texto = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    texto = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", texto.strip())
    dados = json.loads(texto)
    if isinstance(dados, list) and dados and isinstance(dados[0], dict):
        dados = dados[0]
    if not isinstance(dados, dict):
        raise ValueError(f"Resposta da Gemini não é um objeto JSON: {type(dados).__name__}")
    return dados


def _finalizar(plano: _Plano, dados: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """Valida a resposta do LLM campo a campo, caindo para a Camada 1 quando necessário.

    Títulos já informativos (não vagos) nunca são alterados nem truncados.
    """
    titulo_final = plano.titulo_heuristico
    resumo_final = plano.resumo_heuristico
    if dados is None:
        return titulo_final, resumo_final

    if plano.titulo_vago:
        titulo_llm = dados.get("titulo")
        titulo_llm = " ".join(titulo_llm.split()).strip(" \"'") if isinstance(titulo_llm, str) else ""
        if titulo_llm and not is_vague_title(titulo_llm):
            titulo_final = truncar_titulo(titulo_llm, MAX_TITULO_CHARS)
        else:
            logger.warning(f"Gemini retornou título vago/inválido ({titulo_llm!r}); usando heurística local.")

    resumo_llm = dados.get("resumo")
    if isinstance(resumo_llm, str) and not is_generic_summary(resumo_llm, titulo_final):
        resumo_final = truncar_texto(resumo_llm, MAX_RESUMO_CHARS)
    else:
        logger.warning("Gemini retornou resumo vazio/genérico; usando heurística local.")

    return titulo_final, resumo_final


def _log_falha(exc: Exception) -> None:
    logger.warning(f"Falha na chamada à Gemini API ({type(exc).__name__}: {exc}); usando heurística local.")


def enrich_title_and_summary(
    titulo: Optional[str],
    texto_extraido: Optional[str] = None,
    assunto: Optional[str] = None,
    orgao_emissor: Optional[str] = None,
    url_pdf: Optional[str] = None,
    resumo_atual: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Retorna ``(titulo, resumo)`` normalizados combinando heurística local e Gemini (síncrono).

    Nunca levanta exceção: qualquer falha na Camada 2 resulta no resultado da Camada 1.
    """
    try:
        plano = _planejar(titulo, texto_extraido, assunto, orgao_emissor, url_pdf, resumo_atual)
    except Exception as exc:  # pragma: no cover - salvaguarda final do pipeline
        logger.warning(f"Falha inesperada na heurística de título/resumo: {exc}")
        return (titulo or "Edital sem título").strip()[:MAX_TITULO_CHARS], resumo_atual

    if plano.prompt is None:
        return _finalizar(plano, None)

    dados: Optional[Dict[str, Any]] = None
    try:
        url, headers, body = _request_args(plano.prompt)
        with _build_client(settings.GEMINI_TIMEOUT_SECONDS) as client:
            dados = _parse_resposta(client.post(url, headers=headers, json=body))
    except Exception as exc:
        _log_falha(exc)
    return _finalizar(plano, dados)


async def enrich_title_and_summary_async(
    titulo: Optional[str],
    texto_extraido: Optional[str] = None,
    assunto: Optional[str] = None,
    orgao_emissor: Optional[str] = None,
    url_pdf: Optional[str] = None,
    resumo_atual: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Versão assíncrona de :func:`enrich_title_and_summary` (mesmas regras de fallback)."""
    try:
        plano = _planejar(titulo, texto_extraido, assunto, orgao_emissor, url_pdf, resumo_atual)
    except Exception as exc:  # pragma: no cover - salvaguarda final do pipeline
        logger.warning(f"Falha inesperada na heurística de título/resumo: {exc}")
        return (titulo or "Edital sem título").strip()[:MAX_TITULO_CHARS], resumo_atual

    if plano.prompt is None:
        return _finalizar(plano, None)

    dados: Optional[Dict[str, Any]] = None
    try:
        url, headers, body = _request_args(plano.prompt)
        async with _build_async_client(settings.GEMINI_TIMEOUT_SECONDS) as client:
            dados = _parse_resposta(await client.post(url, headers=headers, json=body))
    except Exception as exc:
        _log_falha(exc)
    return _finalizar(plano, dados)


def summarize_edital(
    titulo: Optional[str],
    texto_extraido: Optional[str] = None,
    assunto: Optional[str] = None,
    orgao_emissor: Optional[str] = None,
    url_pdf: Optional[str] = None,
    resumo_atual: Optional[str] = None,
) -> Optional[str]:
    """Atalho que retorna apenas o resumo produzido por :func:`enrich_title_and_summary`."""
    return enrich_title_and_summary(titulo, texto_extraido, assunto, orgao_emissor, url_pdf, resumo_atual)[1]


async def summarize_edital_async(
    titulo: Optional[str],
    texto_extraido: Optional[str] = None,
    assunto: Optional[str] = None,
    orgao_emissor: Optional[str] = None,
    url_pdf: Optional[str] = None,
    resumo_atual: Optional[str] = None,
) -> Optional[str]:
    """Atalho assíncrono que retorna apenas o resumo."""
    _, resumo = await enrich_title_and_summary_async(
        titulo, texto_extraido, assunto, orgao_emissor, url_pdf, resumo_atual
    )
    return resumo
