import { obterTokenStorage } from '@/utils/authStorage';

/**
 * Normaliza a URL base da API garantindo fallback local e ausência de barra final.
 */
export function resolveApiBaseUrl(rawUrl?: string): string {
  const trimmed = rawUrl?.trim();
  const base = trimmed && trimmed.length > 0 ? trimmed : 'http://localhost:8000';
  return base.replace(/\/+$/, '');
}

export const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

export const GET_TIMEOUT_MS = 45_000;
export const MUTATION_TIMEOUT_MS = 20_000;
export const MAX_GET_RETRIES = 2;
export const TRANSIENT_STATUS_CODES = new Set([502, 503, 504]);

export const TRANSIENT_ERROR_MESSAGE =
  'Servidor temporariamente indisponível. Tente novamente em instantes.';
export const TIMEOUT_ERROR_MESSAGE =
  'O servidor demorou para responder. Tente novamente em instantes.';

export interface ApiErrorOptions {
  status?: number;
  isTransient?: boolean;
  isTimeout?: boolean;
  detail?: string;
}

/**
 * Erro tipado de comunicação HTTP que preserva status e sinaliza falhas transitórias.
 */
export class ApiError extends Error {
  readonly status?: number;
  readonly isTransient: boolean;
  readonly isTimeout: boolean;
  readonly detail?: string;

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status;
    this.isTransient = Boolean(options.isTransient);
    this.isTimeout = Boolean(options.isTimeout);
    this.detail = options.detail;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

/**
 * Indica se o erro decorre de indisponibilidade temporária (502/503/504, timeout ou rede).
 */
export function isTransientError(error: unknown): boolean {
  return error instanceof ApiError ? error.isTransient : error instanceof TypeError;
}

/**
 * Indica falha explícita de autenticação ou autorização pelo backend (401/403).
 */
export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

/**
 * Retorna cabeçalho Authorization Bearer quando houver token salvo no storage.
 */
export function getAuthHeaders(): Record<string, string> {
  const token = obterTokenStorage();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface ApiRequestOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: BodyInit | null;
  signal?: AbortSignal;
  auth?: boolean;
  requireAuth?: boolean;
  timeoutMs?: number;
  retryDelayMs?: number;
  parseResponse?: 'json' | 'void';
  errorMessage?: string;
}

function createAbortError(): Error {
  if (typeof DOMException !== 'undefined') {
    return new DOMException('Aborted', 'AbortError');
  }
  const error = new Error('Aborted');
  error.name = 'AbortError';
  return error;
}

function sleepWithSignal(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return Promise.reject(createAbortError());
  }

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      globalThis.clearTimeout(timerId);
      reject(createAbortError());
    };

    const timerId = globalThis.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);

    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function mergeHeaders(
  auth?: boolean,
  customHeaders?: Record<string, string>,
): Record<string, string> {
  const result: Record<string, string> = {};
  if (auth) {
    Object.assign(result, getAuthHeaders());
  }
  if (customHeaders) {
    Object.assign(result, customHeaders);
  }
  return result;
}

async function extractDetailString(response: Response): Promise<string | undefined> {
  try {
    const contentType = response.headers?.get?.('content-type') ?? '';
    if (contentType.toLowerCase().includes('text/html')) {
      return undefined;
    }
    const body = (await response.json()) as { detail?: unknown } | null;
    if (body && typeof body.detail === 'string' && body.detail.trim()) {
      return body.detail.trim();
    }
  } catch {
    // Mantém detail indefinido para respostas sem JSON válido.
  }
  return undefined;
}

/**
 * Executa requisição HTTP centralizada com timeout, composição de AbortSignal
 * e retry exponencial estrito para requisições GET em falhas transitórias.
 */
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  if (options.requireAuth && !obterTokenStorage()) {
    throw new ApiError('Usuário não autenticado.', {
      status: 401,
      isTransient: false,
    });
  }

  const method = (options.method ?? 'GET').toUpperCase();
  const timeoutMs =
    options.timeoutMs ?? (method === 'GET' ? GET_TIMEOUT_MS : MUTATION_TIMEOUT_MS);
  const allowedRetries = method === 'GET' ? MAX_GET_RETRIES : 0;
  const baseDelay =
    options.retryDelayMs ?? (import.meta.env.MODE === 'test' ? 10 : 1_000);
  const parseResponse = options.parseResponse ?? 'json';
  const externalSignal = options.signal;
  const mergedHeaders = mergeHeaders(options.auth || options.requireAuth, options.headers);

  for (let attempt = 0; attempt <= allowedRetries; attempt++) {
    if (externalSignal?.aborted) {
      throw createAbortError();
    }

    const attemptController = new AbortController();
    let timedOut = false;

    const timerId = globalThis.setTimeout(() => {
      timedOut = true;
      attemptController.abort();
    }, timeoutMs);

    const onExternalAbort = () => {
      attemptController.abort();
    };
    externalSignal?.addEventListener('abort', onExternalAbort, { once: true });

    let shouldRetry = false;

    try {
      const fetchInit: RequestInit = {
        method,
        signal: attemptController.signal,
      };
      if (Object.keys(mergedHeaders).length > 0) {
        fetchInit.headers = mergedHeaders;
      }
      if (options.body !== undefined) {
        fetchInit.body = options.body;
      }

      const response = await fetch(`${API_BASE_URL}${path}`, fetchInit);

      if (!response.ok) {
        const isTransient = TRANSIENT_STATUS_CODES.has(response.status);
        if (isTransient && attempt < allowedRetries) {
          shouldRetry = true;
        } else {
          const detail = await extractDetailString(response);
          const message = isTransient
            ? TRANSIENT_ERROR_MESSAGE
            : detail ||
              options.errorMessage ||
              `Erro na requisição (${response.status}).`;

          throw new ApiError(message, {
            status: response.status,
            isTransient,
            detail,
          });
        }
      } else if (parseResponse === 'void') {
        return undefined as T;
      } else {
        const contentType = response.headers?.get?.('content-type') ?? '';
        if (contentType.toLowerCase().includes('text/html')) {
          throw new ApiError('Resposta inválida do servidor.', {
            status: response.status,
            isTransient: true,
          });
        }

        try {
          return (await response.json()) as T;
        } catch {
          throw new ApiError('Resposta inválida do servidor.', {
            status: response.status,
            isTransient: true,
          });
        }
      }
    } catch (err: unknown) {
      if (externalSignal?.aborted) {
        throw createAbortError();
      }
      if (timedOut) {
        throw new ApiError(TIMEOUT_ERROR_MESSAGE, {
          isTransient: true,
          isTimeout: true,
        });
      }
      if (err instanceof ApiError) {
        throw err;
      }
      if (err instanceof TypeError) {
        if (attempt < allowedRetries) {
          shouldRetry = true;
        } else {
          throw new ApiError(TRANSIENT_ERROR_MESSAGE, { isTransient: true });
        }
      } else {
        throw err;
      }
    } finally {
      globalThis.clearTimeout(timerId);
      externalSignal?.removeEventListener('abort', onExternalAbort);
    }

    if (shouldRetry) {
      await sleepWithSignal(baseDelay * 2 ** attempt, externalSignal);
    }
  }

  throw new ApiError(TRANSIENT_ERROR_MESSAGE, { isTransient: true });
}
