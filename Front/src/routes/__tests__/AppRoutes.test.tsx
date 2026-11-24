import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import AppRoutes from '../AppRoutes';

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    usuario: null,
    autenticado: false,
    carregando: false,
    logout: vi.fn(),
  }),
}));

describe('AppRoutes', () => {
  it('renderiza NotFoundPage com cabeçalho e rodapé ao acessar rota inexistente', () => {
    render(
      <MemoryRouter initialEntries={['/caminho-inexistente']}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Página não encontrada' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Voltar para editais' }),
    ).toHaveAttribute('href', '/');
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });
});
