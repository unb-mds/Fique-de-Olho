/**
 * Lê uma chave do localStorage protegendo contra SecurityError
 * (ex.: WebViews ou modo privado com armazenamento bloqueado).
 */
export function safeStorageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Grava um valor no localStorage protegendo contra SecurityError e QuotaExceededError.
 */
export function safeStorageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Falha silenciosa em ambientes sem armazenamento persistente disponível.
  }
}

/**
 * Remove uma chave do localStorage com segurança contra erros de acesso.
 */
export function safeStorageRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignora falha de acesso ao storage.
  }
}
