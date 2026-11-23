"""Camada 2 — Orquestração híbrida (heurística + LLM) de títulos e resumos de editais.

Issues #77 (resumo automático), #106 (normalização de títulos vagos/genéricos),
#121/#125 (extração estruturada de metadados) e #129 (modelo econômico autônomo
gemini-3.5-flash-lite com fallback de modelo e retry de rate limit).

Fluxo:
1. Calcula sempre o resultado determinístico da Camada 1 (``parser.py``):
   ``reconstruir_titulo_edital`` e ``extrair_objeto_edital``.
2. Se ``GEMINI_API_KEY`` estiver configurada, houver conteúdo textual e o título
   for vago ou o resumo estiver ausente/genérico, faz chamada à
   Google Gemini API (``generateContent``) via ``httpx``.
3. Graceful degradation: ausência de chave, erro HTTP, timeout, JSON inválido ou
   título ainda vago resultam em ``logger.warning`` e fallback transparente para a
   Camada 1 — nenhuma exceção é propagada ao pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.modules.scraper.parser import (
    MAX_RESUMO_CHARS,
    MAX_TITULO_CHARS,
    _TITULOS_GENERICOS,
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

_TRECHO_RELEVANTE_RE = re.compile(
    r"(?:cronograma|calend[aá]rio|das\s+inscri[cç][oõ]es|per[ií]odo\s+de\s+inscri[cç][aã]o|"
    r"prazo\s+(?:de|para)\s+inscri[cç][oõaã]e?s?|prorroga[cç][aã]o|retifica[cç][aã]o|"
    r"valor\s+da\s+bolsa|bolsas?\s+e\s+aux[ií]lios?|das\s+vagas)",
    re.IGNORECASE,
)


def selecionar_trechos_relevantes_prompt(
    texto_extraido: Optional[str],
    max_chars: int = MAX_TEXTO_PROMPT_CHARS,
) -> str:
    """Seleciona trechos de maior valor (início, cronograma/inscrições e fim) dentro do limite."""
    if not texto_extraido or not texto_extraido.strip():
        return ""

    limpo = limpar_texto_documento(texto_extraido)
    if len(limpo) <= max_chars:
        return limpo

    # Orçamento: 45% cabeçalho/objeto, 40% janelas de cronograma/inscrições/bolsa, 15% trecho final
    head_budget = int(max_chars * 0.45)
    tail_budget = int(max_chars * 0.15)
    mid_budget = max_chars - head_budget - tail_budget

    partes: list[str] = [limpo[:head_budget].rstrip()]
    restante = limpo[head_budget:]
    tail_start = max(head_budget, len(limpo) - tail_budget)

    # Coleta janelas não sobrepostas em torno de menções a cronograma/inscrições/bolsa após o cabeçalho
    intervalos: list[tuple[int, int]] = []
    for match in _TRECHO_RELEVANTE_RE.finditer(limpo, pos=head_budget, endpos=tail_start):
        ini = max(head_budget, match.start() - 120)
        fim = min(tail_start, match.end() + 700)
        if intervalos and ini <= intervalos[-1][1]:
            intervalos[-1] = (intervalos[-1][0], max(intervalos[-1][1], fim))
        else:
            intervalos.append((ini, fim))

    usado_mid = 0
    for ini, fim in intervalos:
        if usado_mid >= mid_budget:
            break
        trecho = limpo[ini:fim].strip()
        if not trecho:
            continue
        disp = mid_budget - usado_mid
        if len(trecho) > disp:
            trecho = trecho[:disp].rstrip()
        partes.append(f"[...]\n{trecho}")
        usado_mid += len(trecho)

    tail = limpo[tail_start:].strip()
    if tail and restante:
        partes.append(f"[...]\n{tail}")

    combinado = "\n\n".join(partes)
    return truncar_texto(combinado, max_chars) or combinado[:max_chars]


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


def _is_rotulo_generico(texto: Optional[str]) -> bool:
    """True quando o texto é apenas um rótulo genérico de botão/link (AQUI, Download, Edital...)."""
    key = _norm_key(texto)
    if not key:
        return True
    return key in _TITULOS_GENERICOS or any(key.startswith(p) for p in _RESUMOS_GENERICOS_PREFIXOS)


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
        # Issue #119: rótulos de botão/links ("AQUI", "Clique aqui", "Download") nunca viram resumo.
        if not _is_rotulo_generico(resumo_atual):
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

    texto = selecionar_trechos_relevantes_prompt(texto_extraido, MAX_TEXTO_PROMPT_CHARS) if texto_extraido else ""
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


def _request_args(prompt: str, model: Optional[str] = None) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    alvo = (model or settings.GEMINI_MODEL or "gemini-3.5-flash-lite").strip()
    url = GEMINI_ENDPOINT.format(model=alvo)
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


_RETRY_DELAY_MAX_SECONDS = 10.0


def _retry_delay(resp: httpx.Response) -> float:
    """Espera antes do retry de 429: respeita ``Retry-After`` (limitado) ou usa o delay configurado."""
    try:
        base = float(getattr(settings, "GEMINI_RETRY_DELAY_SECONDS", 2.0) or 0.0)
    except (TypeError, ValueError):
        base = 2.0
    try:
        base = max(base, float(resp.headers.get("retry-after", 0) or 0))
    except (TypeError, ValueError):
        pass
    return min(max(0.0, base), _RETRY_DELAY_MAX_SECONDS)


_RETRYABLE_STATUS_CODES = (429, 502, 503, 504)


def _post_with_retry_sync(
    client: httpx.Client,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> httpx.Response:
    resp = client.post(url, headers=headers, json=body)
    if resp.status_code in _RETRYABLE_STATUS_CODES:
        delay = _retry_delay(resp)
        logger.warning(
            f"Erro transitório (HTTP {resp.status_code}) na Gemini API; "
            f"aguardando {delay:.1f}s antes de 1 nova tentativa."
        )
        if delay > 0:
            time.sleep(delay)
        resp = client.post(url, headers=headers, json=body)
    return resp


async def _post_with_retry_async(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> httpx.Response:
    resp = await client.post(url, headers=headers, json=body)
    if resp.status_code in _RETRYABLE_STATUS_CODES:
        delay = _retry_delay(resp)
        logger.warning(
            f"Erro transitório (HTTP {resp.status_code}) na Gemini API; "
            f"aguardando {delay:.1f}s antes de 1 nova tentativa."
        )
        if delay > 0:
            await asyncio.sleep(delay)
        resp = await client.post(url, headers=headers, json=body)
    return resp


def _call_gemini_sync(prompt: str) -> Dict[str, Any]:
    """Executa chamada síncrona ao Gemini com retry em 429/503 e fallback automático de modelo em 404."""
    primary_model = (settings.GEMINI_MODEL or "gemini-3.5-flash-lite").strip()
    fallback_model = (getattr(settings, "GEMINI_FALLBACK_MODEL", "") or "").strip()
    url, headers, body = _request_args(prompt, model=primary_model)
    with _build_client(settings.GEMINI_TIMEOUT_SECONDS) as client:
        resp = _post_with_retry_sync(client, url, headers, body)
        if resp.status_code == 404 and fallback_model and fallback_model != primary_model:
            logger.warning(
                f"Modelo Gemini '{primary_model}' retornou HTTP 404; tentando fallback '{fallback_model}'."
            )
            fb_url, fb_headers, fb_body = _request_args(prompt, model=fallback_model)
            resp = _post_with_retry_sync(client, fb_url, fb_headers, fb_body)
        return _parse_resposta(resp)


async def _call_gemini_async(prompt: str) -> Dict[str, Any]:
    """Executa chamada assíncrona ao Gemini com retry em 429/503 e fallback automático de modelo em 404."""
    primary_model = (settings.GEMINI_MODEL or "gemini-3.5-flash-lite").strip()
    fallback_model = (getattr(settings, "GEMINI_FALLBACK_MODEL", "") or "").strip()
    url, headers, body = _request_args(prompt, model=primary_model)
    async with _build_async_client(settings.GEMINI_TIMEOUT_SECONDS) as client:
        resp = await _post_with_retry_async(client, url, headers, body)
        if resp.status_code == 404 and fallback_model and fallback_model != primary_model:
            logger.warning(
                f"Modelo Gemini '{primary_model}' retornou HTTP 404; tentando fallback '{fallback_model}'."
            )
            fb_url, fb_headers, fb_body = _request_args(prompt, model=fallback_model)
            resp = await _post_with_retry_async(client, fb_url, fb_headers, fb_body)
        return _parse_resposta(resp)


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
        dados = _call_gemini_sync(plano.prompt)
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
        dados = await _call_gemini_async(plano.prompt)
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


# ---------------------------------------------------------------------------
# Extração Estruturada de Metadados via LLM (Issue #121)
# ---------------------------------------------------------------------------


def _parse_llm_date(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or val.lower() == "null":
        return None
    # YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", val)
    if m_iso:
        try:
            return datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass
    # DD/MM/YYYY
    m_slash = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", val)
    if m_slash:
        try:
            return datetime(int(m_slash.group(3)), int(m_slash.group(2)), int(m_slash.group(1)), tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _converter_metadados_llm(dados: Dict[str, Any]) -> Dict[str, Any]:
    resultado: Dict[str, Any] = {}
    if not isinstance(dados, dict):
        return resultado

    ini = _parse_llm_date(dados.get("inicio_inscricao"))
    if ini:
        resultado["inicio_inscricao"] = ini

    fim = _parse_llm_date(dados.get("fim_inscricao"))
    if fim:
        resultado["fim_inscricao"] = fim

    val = dados.get("valor_bolsa")
    if isinstance(val, (int, float)) and 0 < val <= 15000:
        resultado["valor_bolsa"] = float(val)
        resultado["tem_bolsa"] = True
    elif isinstance(val, str):
        try:
            cleaned_num = re.sub(r"[rR]\$\s*", "", val).replace(".", "").replace(",", ".").strip()
            num = float(cleaned_num)
            if 0 < num <= 15000:
                resultado["valor_bolsa"] = num
                resultado["tem_bolsa"] = True
        except ValueError:
            pass

    if "tem_bolsa" not in resultado:
        tb = dados.get("tem_bolsa")
        if isinstance(tb, bool):
            resultado["tem_bolsa"] = tb

    vagas = dados.get("vagas")
    if isinstance(vagas, int) and 0 < vagas < 100000:
        resultado["vagas"] = vagas
    elif isinstance(vagas, str) and vagas.isdigit():
        iv = int(vagas)
        if 0 < iv < 100000:
            resultado["vagas"] = iv

    org = dados.get("orgao_emissor")
    if isinstance(org, str) and org.strip() and org.strip().lower() != "null":
        resultado["orgao_emissor"] = org.strip().upper()

    return resultado


def _montar_prompt_metadados(texto_extraido: Optional[str], titulo: Optional[str]) -> str:
    texto = selecionar_trechos_relevantes_prompt(texto_extraido, MAX_TEXTO_PROMPT_CHARS) if texto_extraido else ""
    return (
        "Você analisa editais da Universidade de Brasília (UnB) e extrai metadados estruturados de oportunidades para estudantes.\n"
        "Responda SOMENTE com um objeto JSON válido no formato:\n"
        '{"inicio_inscricao": "YYYY-MM-DD ou null", '
        '"fim_inscricao": "YYYY-MM-DD ou null", '
        '"valor_bolsa": float_ou_null, '
        '"tem_bolsa": boolean_ou_null, '
        '"vagas": int_ou_null, '
        '"orgao_emissor": "SIGLA_OU_NULL"}\n\n'
        "Regras:\n"
        '- "inicio_inscricao" e "fim_inscricao": prazo de inscrições no formato YYYY-MM-DD. Se houver apenas prazo limite final, preencha no "fim_inscricao".\n'
        '- "valor_bolsa": valor monetário mensal de bolsa/estipêndio do discente (ex.: 700.0). NUNCA extraia taxas de inscrição (ex.: R$ 50,00) nem orçamento global de projeto.\n'
        '- "tem_bolsa": true se houver bolsa remunerada/auxílio financeiro, false se voluntário/sem remuneração, null se não mencionado.\n'
        '- "vagas": quantidade de vagas ofertadas.\n'
        '- "orgao_emissor": sigla do decanato ou unidade responsável (ex.: DEG, DEX, DPG, DPI, DAC, BCE, CAL, etc.).\n\n'
        f"Título do edital: {titulo or '(vazio)'}\n"
        f'Conteúdo do edital (trecho):\n"""\n{texto or "(indisponível)"}\n"""\n'
    )


def _montar_prompt_unificado(
    *,
    titulo: str,
    texto_extraido: Optional[str],
    assunto: Optional[str],
    orgao_emissor: Optional[str],
    url_pdf: Optional[str],
    pedir_titulo: bool,
    pedir_resumo: bool,
    pedir_metadados: bool,
) -> str:
    campos_json: list[str] = []
    regras: list[str] = []

    if pedir_titulo:
        campos_json.append('"titulo": "string"')
        regras.append(
            f'- "titulo": título claro e padronizado em português (máx. {MAX_TITULO_LLM_CHARS} caracteres), '
            "incluindo órgão emissor, programa/número do edital e etapa quando aplicável. "
            "Nunca use termos vagos isolados como Edital, Aqui ou Download."
        )
    if pedir_resumo:
        campos_json.append('"resumo": "string"')
        regras.append(
            f'- "resumo": no máximo 2 frases (até {MAX_RESUMO_CHARS} caracteres) explicando a oportunidade e o '
            "público-alvo para estudantes da UnB. Não invente informações que não estejam no conteúdo."
        )
    if pedir_metadados:
        campos_json.extend(
            [
                '"inicio_inscricao": "YYYY-MM-DD ou null"',
                '"fim_inscricao": "YYYY-MM-DD ou null"',
                '"valor_bolsa": float_ou_null',
                '"tem_bolsa": boolean_ou_null',
                '"vagas": int_ou_null',
                '"orgao_emissor": "SIGLA_OU_NULL"',
            ]
        )
        regras.extend(
            [
                '- "inicio_inscricao" e "fim_inscricao": prazo de inscrições no formato YYYY-MM-DD. Se houver apenas prazo limite final, preencha em "fim_inscricao".',
                '- "valor_bolsa": valor monetário mensal da bolsa/auxílio ao estudante (ex.: 700.0). NUNCA extraia taxa de inscrição ou orçamento global.',
                '- "tem_bolsa": true se houver bolsa/auxílio, false se voluntário/sem remuneração, null se não informado.',
                '- "vagas": quantidade total de vagas ofertadas.',
                '- "orgao_emissor": sigla da unidade/decanato responsável (ex.: DEG, DEX, DPG, DPI, DAC, CEAD).',
            ]
        )

    texto = selecionar_trechos_relevantes_prompt(texto_extraido, MAX_TEXTO_PROMPT_CHARS) if texto_extraido else ""
    formato = "{" + ", ".join(campos_json) + "}"
    regras_str = "\n".join(regras)
    return (
        "Você analisa e organiza editais da Universidade de Brasília (UnB) para estudantes.\n"
        f"Responda SOMENTE com um objeto JSON válido no formato {formato}.\n"
        "Regras:\n"
        f"{regras_str}\n\n"
        f"Título atual: {titulo or '(vazio)'}\n"
        f"Órgão emissor: {orgao_emissor or '(não informado)'}\n"
        f"Assunto: {assunto or '(não informado)'}\n"
        f"Link do PDF: {url_pdf or '(não informado)'}\n"
        f'Conteúdo do edital (trechos relevantes):\n"""\n{texto or "(indisponível)"}\n"""\n'
    )


def enrich_edital_with_llm(
    *,
    titulo: Optional[str],
    texto_extraido: Optional[str] = None,
    assunto: Optional[str] = None,
    orgao_emissor: Optional[str] = None,
    url_pdf: Optional[str] = None,
    resumo_atual: Optional[str] = None,
    pedir_metadados: bool = True,
) -> Dict[str, Any]:
    """Segunda passada unificada (Camada 2): extrai título/resumo e metadados ausentes em 1 única chamada.

    Sempre calcula a Camada 1 local para título/resumo. Só chama a Gemini API se houver
    ``GEMINI_API_KEY``, conteúdo textual/assunto e algum campo pendente (título vago,
    resumo genérico ou metadados solicitados). Nunca propaga exceções.
    """
    global _missing_key_warned

    titulo_str = (titulo or "").strip()
    titulo_vago = is_vague_title(titulo_str)
    titulo_heur = reconstruir_titulo_edital(titulo_str, texto_extraido, assunto, orgao_emissor, url_pdf)
    resumo_heur = _resumo_heuristico(titulo_str, texto_extraido, assunto, resumo_atual)
    pedir_resumo = is_generic_summary(resumo_atual, titulo_str)

    resultado: Dict[str, Any] = {
        "titulo": titulo_heur,
        "resumo": resumo_heur,
    }

    tem_conteudo = bool((texto_extraido and texto_extraido.strip()) or (assunto and assunto.strip()))
    precisa_llm = tem_conteudo and (titulo_vago or pedir_resumo or pedir_metadados)
    if not precisa_llm:
        return resultado

    if not settings.GEMINI_API_KEY:
        if not _missing_key_warned:
            logger.warning(
                "GEMINI_API_KEY não configurada; títulos/resumos e metadados usarão apenas a Camada 1 local."
            )
            _missing_key_warned = True
        return resultado

    prompt = _montar_prompt_unificado(
        titulo=titulo_str,
        texto_extraido=texto_extraido,
        assunto=assunto,
        orgao_emissor=orgao_emissor,
        url_pdf=url_pdf,
        pedir_titulo=titulo_vago,
        pedir_resumo=pedir_resumo,
        pedir_metadados=pedir_metadados,
    )

    try:
        dados = _call_gemini_sync(prompt)
    except Exception as exc:
        _log_falha(exc)
        return resultado

    if titulo_vago:
        titulo_llm = dados.get("titulo")
        titulo_llm = " ".join(titulo_llm.split()).strip(" \"'") if isinstance(titulo_llm, str) else ""
        if titulo_llm and not is_vague_title(titulo_llm):
            resultado["titulo"] = truncar_titulo(titulo_llm, MAX_TITULO_CHARS)
        else:
            logger.warning(f"Gemini retornou título vago/inválido ({titulo_llm!r}); usando heurística local.")

    if pedir_resumo:
        resumo_llm = dados.get("resumo")
        if isinstance(resumo_llm, str) and not is_generic_summary(resumo_llm, resultado["titulo"]):
            resultado["resumo"] = truncar_texto(resumo_llm, MAX_RESUMO_CHARS)
        else:
            logger.warning("Gemini retornou resumo vazio/genérico; usando heurística local.")

    if pedir_metadados:
        resultado.update(_converter_metadados_llm(dados))

    return resultado


def enrich_metadata_with_llm(
    texto_extraido: Optional[str],
    titulo: Optional[str] = None,
) -> Dict[str, Any]:
    """Extrai metadados estruturados (datas, bolsa, vagas, órgão) via Gemini (Camada 2).

    Fallback gracioso: se a API não estiver configurada, ocorrer erro de rede, timeout
    ou resposta malformada, captura a exceção e retorna dicionário vazio {}.
    """
    if not settings.GEMINI_API_KEY:
        return {}
    if not texto_extraido or not texto_extraido.strip():
        return {}

    try:
        prompt = _montar_prompt_metadados(texto_extraido, titulo)
        dados = _call_gemini_sync(prompt)
        return _converter_metadados_llm(dados)
    except Exception as exc:
        logger.warning(f"Falha ao enriquecer metadados com Gemini ({type(exc).__name__}: {exc}); usando dados locais.")
        return {}


async def enrich_metadata_with_llm_async(
    texto_extraido: Optional[str],
    titulo: Optional[str] = None,
) -> Dict[str, Any]:
    """Versão assíncrona de :func:`enrich_metadata_with_llm`."""
    if not settings.GEMINI_API_KEY:
        return {}
    if not texto_extraido or not texto_extraido.strip():
        return {}

    try:
        prompt = _montar_prompt_metadados(texto_extraido, titulo)
        dados = await _call_gemini_async(prompt)
        return _converter_metadados_llm(dados)
    except Exception as exc:
        logger.warning(f"Falha assíncrona ao enriquecer metadados com Gemini ({type(exc).__name__}: {exc}); usando dados locais.")
        return {}
