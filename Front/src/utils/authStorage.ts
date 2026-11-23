import {
  safeStorageGet,
  safeStorageRemove,
  safeStorageSet,
} from '@/utils/storage';
import type { Usuario } from '@/services/authService';

const TOKEN_STORAGE_KEY = 'token';
const USUARIO_STORAGE_KEY = 'usuario';

type JwtExpirationResult = { expired: true } | { expMs: number | null; expired?: false };

function inspecionarExpiracaoJwt(token: string): JwtExpirationResult {
  const parts = token.split('.');
  if (parts.length !== 3) {
    return { expMs: null };
  }

  try {
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const padLength = (4 - (base64.length % 4)) % 4;
    const padded = base64 + '='.repeat(padLength);
    const jsonPayload = atob(padded);
    const payload = JSON.parse(jsonPayload) as { exp?: unknown } | null;

    if (payload && typeof payload.exp === 'number' && Number.isFinite(payload.exp)) {
      return { expMs: payload.exp * 1000 };
    }

    return { expMs: null };
  } catch {
    return { expired: true };
  }
}

/**
 * Obtém o token JWT salvo no localStorage com segurança.
 */
export function obterTokenStorage(): string | null {
  return safeStorageGet(TOKEN_STORAGE_KEY);
}

/**
 * Persiste token e dados básicos do usuário no localStorage com segurança.
 */
export function salvarSessaoStorage(token: string, usuario: Usuario): void {
  safeStorageSet(TOKEN_STORAGE_KEY, token);
  safeStorageSet(USUARIO_STORAGE_KEY, JSON.stringify(usuario));
}

/**
 * Remove token e dados do usuário persistidos no localStorage.
 */
export function limparSessaoStorage(): void {
  safeStorageRemove(TOKEN_STORAGE_KEY);
  safeStorageRemove(USUARIO_STORAGE_KEY);
}

/**
 * Verifica localmente se um token JWT está expirado segundo o relógio do cliente.
 */
export function tokenLocalExpirado(token: string, nowMs = Date.now()): boolean {
  const resultado = inspecionarExpiracaoJwt(token);
  if (resultado.expired) {
    return true;
  }
  if (resultado.expMs === null) {
    return false;
  }
  return resultado.expMs <= nowMs;
}

/**
 * Lê e valida o objeto Usuario cacheado no localStorage.
 * Retorna `null` se estiver ausente, malformado ou sem os campos obrigatórios.
 */
export function lerUsuarioCacheado(): Usuario | null {
  const raw = safeStorageGet(USUARIO_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<Usuario> | null;
    if (
      parsed &&
      typeof parsed === 'object' &&
      typeof parsed.id === 'number' &&
      typeof parsed.nome === 'string' &&
      typeof parsed.email === 'string'
    ) {
      return {
        id: parsed.id,
        nome: parsed.nome,
        email: parsed.email,
        receber_emails: Boolean(parsed.receber_emails),
      };
    }
  } catch {
    return null;
  }

  return null;
}
