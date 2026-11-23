import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '../LoginPage';
import { ApiError } from '@/services/apiClient';
import { login } from '@/services/authService';

vi.mock('@/services/authService', () => ({
  login: vi.fn(),
  loginWithGoogle: vi.fn(),
}));

vi.mock('@/services/favoritosService', () => ({
  favoritarEdital: vi.fn(),
}));

vi.mock('@/services/notificacoesService', () => ({
  ativarAlertaEdital: vi.fn(),
}));

vi.mock('@/components/GoogleSignInButton', () => ({
  GoogleSignInButton: () => <div>GoogleSignInMock</div>,
}));

describe('LoginPage', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('exibe mensagem de indisponibilidade real em erro 503 em vez de mascarar como senha inválida', async () => {
    vi.mocked(login).mockRejectedValueOnce(
      new ApiError('Servidor temporariamente indisponível. Tente novamente em instantes.', {
        status: 503,
        isTransient: true,
      }),
    );

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'ana@unb.br' } });
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Servidor temporariamente indisponível. Tente novamente em instantes.',
    );
    expect(alert).not.toHaveTextContent('E-mail ou senha inválidos.');
  });

  it('bloqueia open redirect com // ou /\\ em returnTo', async () => {
    for (const unsafeTarget of ['//evil.com', '/\\evil.com']) {
      const locationMock = { href: 'http://localhost/login', pathname: '/login' };
      Object.defineProperty(window, 'location', {
        value: locationMock,
        writable: true,
        configurable: true,
      });

      vi.mocked(login).mockResolvedValueOnce({
        access_token: 'jwt',
        token_type: 'bearer',
        usuario: {
          id: 1,
          nome: 'Ana',
          email: 'ana@unb.br',
          receber_emails: true,
        },
      });

      const { unmount } = render(
        <MemoryRouter initialEntries={[{ pathname: '/login', state: { returnTo: unsafeTarget } }]}>
          <LoginPage />
        </MemoryRouter>,
      );

      fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'ana@unb.br' } });
      fireEvent.change(screen.getByLabelText('Senha'), { target: { value: '123456' } });
      fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));

      await waitFor(() => {
        expect(locationMock.href).toBe('/');
      });

      unmount();
    }
  });
});
