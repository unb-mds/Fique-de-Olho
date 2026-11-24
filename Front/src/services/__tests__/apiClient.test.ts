import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  apiRequest,
  GET_TIMEOUT_MS,
  MUTATION_TIMEOUT_MS,
  resolveApiBaseUrl,
  TIMEOUT_ERROR_MESSAGE,
  TRANSIENT_ERROR_MESSAGE,
} from '../apiClient';

function createJsonResponse(body: unknown, status = 200, contentType = 'application/json') {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': contentType },
  });
}

describe('apiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('resolveApiBaseUrl', () => {
    it('usa fallback localhost quando vazia ou indefinida e remove barra final', () => {
      expect(resolveApiBaseUrl(undefined)).toBe('http://localhost:8000');
      expect(resolveApiBaseUrl('')).toBe('http://localhost:8000');
      expect(resolveApiBaseUrl('   ')).toBe('http://localhost:8000');
      expect(resolveApiBaseUrl('https://api.exemplo.com///')).toBe('https://api.exemplo.com');
      expect(resolveApiBaseUrl('  https://api.exemplo.com/  ')).toBe('https://api.exemplo.com');
    });
  });

  it('define timeouts apropriados para cold start em GET e mutações', () => {
    expect(GET_TIMEOUT_MS).toBe(45_000);
    expect(MUTATION_TIMEOUT_MS).toBe(20_000);
  });

  it('faz retry automático em GET para 502/503/504 e falha de rede até recuperar', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(createJsonResponse({ detail: 'Bad Gateway' }, 502))
      .mockResolvedValueOnce(createJsonResponse({ detail: 'Gateway Timeout' }, 504))
      .mockResolvedValueOnce(createJsonResponse({ ok: true }, 200));

    const result = await apiRequest<{ ok: boolean }>('/api/v1/editais/', {
      method: 'GET',
      retryDelayMs: 1,
    });

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);

    vi.restoreAllMocks();

    const fetchNetMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(createJsonResponse({ detail: 'Unavailable' }, 503))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(createJsonResponse({ recovered: true }, 200));

    const netResult = await apiRequest<{ recovered: boolean }>('/api/v1/editais/', {
      method: 'GET',
      retryDelayMs: 1,
    });

    expect(netResult).toEqual({ recovered: true });
    expect(fetchNetMock).toHaveBeenCalledTimes(3);
  });

  it('lança ApiError transitório quando GET esgota todos os retries em 503', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(createJsonResponse({ detail: 'Service Unavailable' }, 503));

    await expect(
      apiRequest('/api/v1/editais/', { method: 'GET', retryDelayMs: 1 }),
    ).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      isTransient: true,
      isTimeout: false,
      message: TRANSIENT_ERROR_MESSAGE,
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('lança ApiError transitório com isTimeout quando GET excede timeout sem retry em loop', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    });

    await expect(
      apiRequest('/api/v1/editais/', { method: 'GET', timeoutMs: 20, retryDelayMs: 1 }),
    ).rejects.toMatchObject({
      name: 'ApiError',
      isTransient: true,
      isTimeout: true,
      message: TIMEOUT_ERROR_MESSAGE,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('NUNCA executa retry em POST, PATCH ou DELETE mesmo em 503, rede ou timeout', async () => {
    for (const method of ['POST', 'PATCH', 'DELETE']) {
      const fetch503 = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce(createJsonResponse({ detail: 'Busy' }, 503));

      await expect(
        apiRequest('/api/v1/auth/register', { method, retryDelayMs: 1 }),
      ).rejects.toMatchObject({ status: 503, isTransient: true });
      expect(fetch503).toHaveBeenCalledTimes(1);
      vi.restoreAllMocks();

      const fetchNetwork = vi
        .spyOn(globalThis, 'fetch')
        .mockRejectedValueOnce(new TypeError('NetworkError'));

      await expect(
        apiRequest('/api/v1/auth/register', { method, retryDelayMs: 1 }),
      ).rejects.toMatchObject({ isTransient: true });
      expect(fetchNetwork).toHaveBeenCalledTimes(1);
      vi.restoreAllMocks();
    }
  });

  it('respeita AbortSignal externo sem disparar retry ao cancelar busca ou backoff', async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      controller.abort();
      return createJsonResponse({ detail: 'Busy' }, 503);
    });

    await expect(
      apiRequest('/api/v1/editais/?q=bolsa', {
        method: 'GET',
        signal: controller.signal,
        retryDelayMs: 50,
      }),
    ).rejects.toMatchObject({ name: 'AbortError' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('rejeita HTTP 200 HTML com ApiError transitório em vez de SyntaxError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('<!doctype html><html></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      }),
    );

    await expect(apiRequest('/api/v1/editais/')).rejects.toBeInstanceOf(ApiError);
  });

  it('não gera "[object Object]" quando backend retorna 422 com detail array', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      createJsonResponse(
        { detail: [{ loc: ['body', 'email'], msg: 'invalid' }] },
        422,
      ),
    );

    await expect(
      apiRequest('/api/v1/auth/register', {
        method: 'POST',
        errorMessage: 'Dados inválidos.',
      }),
    ).rejects.toMatchObject({
      status: 422,
      isTransient: false,
      message: 'Dados inválidos.',
    });
  });
});
