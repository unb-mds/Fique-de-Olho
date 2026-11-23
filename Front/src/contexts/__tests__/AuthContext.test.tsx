import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../AuthContext';
import { ApiError } from '@/services/apiClient';
import { getCurrentUser } from '@/services/authService';
import { limparCacheFavoritos } from '@/services/favoritosService';
import { limparCacheAlertas } from '@/services/notificacoesService';

vi.mock('@/services/authService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/authService')>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    updateEmailPreference: vi.fn(),
  };
});

vi.mock('@/services/favoritosService', () => ({
  limparCacheFavoritos: vi.fn(),
}));

vi.mock('@/services/notificacoesService', () => ({
  limparCacheAlertas: vi.fn(),
}));

function makeJwt(expOffsetSeconds: number): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).replace(/=/g, '');
  const exp = Math.floor(Date.now() / 1000) + expOffsetSeconds;
  const payload = btoa(JSON.stringify({ sub: '1', exp })).replace(/=/g, '');
  return `${header}.${payload}.assinatura`;
}

function AuthProbe() {
  const { usuario, autenticado, carregando } = useAuth();
  return (
    <div>
      <span data-testid="carregando">{String(carregando)}</span>
      <span data-testid="autenticado">{String(autenticado)}</span>
      <span data-testid="nome">{usuario?.nome ?? 'nenhum'}</span>
    </div>
  );
}

describe('AuthContext resiliência', () => {
  const mockUsuario = {
    id: 1,
    nome: 'Maria UnB',
    email: 'maria@unb.br',
    receber_emails: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('mantém token e hidrata usuário cacheado durante falha 503 se JWT local ainda for válido', async () => {
    const validToken = makeJwt(3600);
    localStorage.setItem('token', validToken);
    localStorage.setItem('usuario', JSON.stringify(mockUsuario));

    vi.mocked(getCurrentUser).mockRejectedValueOnce(
      new ApiError('Servidor indisponível', { status: 503, isTransient: true }),
    );

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('carregando')).toHaveTextContent('false');
    });

    expect(screen.getByTestId('autenticado')).toHaveTextContent('true');
    expect(screen.getByTestId('nome')).toHaveTextContent('Maria UnB');
    expect(localStorage.getItem('token')).toBe(validToken);
    expect(limparCacheFavoritos).not.toHaveBeenCalled();
    expect(limparCacheAlertas).not.toHaveBeenCalled();
  });

  it('desloga durante 503 se o token JWT armazenado já estiver expirado localmente', async () => {
    const expiredToken = makeJwt(-60);
    localStorage.setItem('token', expiredToken);
    localStorage.setItem('usuario', JSON.stringify(mockUsuario));

    vi.mocked(getCurrentUser).mockRejectedValueOnce(
      new ApiError('Servidor indisponível', { status: 503, isTransient: true }),
    );

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('carregando')).toHaveTextContent('false');
    });

    expect(screen.getByTestId('autenticado')).toHaveTextContent('false');
    expect(localStorage.getItem('token')).toBeNull();
    expect(localStorage.getItem('usuario')).toBeNull();
    expect(limparCacheFavoritos).toHaveBeenCalledTimes(1);
    expect(limparCacheAlertas).toHaveBeenCalledTimes(1);
  });

  it('limpa sessão e caches quando /auth/me responde HTTP 401 ou 403 explícito', async () => {
    for (const status of [401, 403]) {
      vi.clearAllMocks();
      localStorage.clear();

      const validToken = makeJwt(3600);
      localStorage.setItem('token', validToken);
      localStorage.setItem('usuario', JSON.stringify(mockUsuario));

      vi.mocked(getCurrentUser).mockRejectedValueOnce(
        new ApiError('Não autorizado', { status, isTransient: false }),
      );

      const { unmount } = render(
        <AuthProvider>
          <AuthProbe />
        </AuthProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('carregando')).toHaveTextContent('false');
      });

      expect(screen.getByTestId('autenticado')).toHaveTextContent('false');
      expect(localStorage.getItem('token')).toBeNull();
      expect(localStorage.getItem('usuario')).toBeNull();
      expect(limparCacheFavoritos).toHaveBeenCalledTimes(1);
      expect(limparCacheAlertas).toHaveBeenCalledTimes(1);
      unmount();
    }
  });

  it('tolera JSON corrompido ou shape incompleto no localStorage sem quebrar a renderização', async () => {
    for (const payload of ['{json-corrompido', JSON.stringify({ id: 1, email: 'a@b.com' })]) {
      localStorage.setItem('token', makeJwt(3600));
      localStorage.setItem('usuario', payload);

      vi.mocked(getCurrentUser).mockRejectedValueOnce(new TypeError('Failed to fetch'));

      const { unmount } = render(
        <AuthProvider>
          <AuthProbe />
        </AuthProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('carregando')).toHaveTextContent('false');
      });

      expect(screen.getByTestId('autenticado')).toHaveTextContent('false');
      expect(screen.getByTestId('nome')).toHaveTextContent('nenhum');
      unmount();
    }
  });

  it('finaliza carregando mesmo quando localStorage lança SecurityError', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError');
    });

    await act(async () => {
      render(
        <AuthProvider>
          <AuthProbe />
        </AuthProvider>,
      );
    });

    expect(screen.getByTestId('carregando')).toHaveTextContent('false');
    expect(screen.getByTestId('autenticado')).toHaveTextContent('false');
  });
});
