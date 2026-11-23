import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Header from '../Header';

const useAuthMock = vi.fn();

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => useAuthMock(),
}));

describe('Header', () => {
  it('renderiza fallback seguro quando usuario.nome está ausente ou vazio', () => {
    useAuthMock.mockReturnValue({
      autenticado: true,
      usuario: {
        id: 1,
        nome: undefined as unknown as string,
        email: 'estudante@unb.br',
        receber_emails: false,
      },
      logout: vi.fn(),
    });

    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    expect(screen.getByText('Usuário')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'Abrir perfil de Usuário e ver favoritos',
      }),
    ).toBeInTheDocument();
  });
});
