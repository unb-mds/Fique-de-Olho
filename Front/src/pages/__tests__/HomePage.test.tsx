import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HomePage from '../HomePage';
import { getEditais } from '@/services/editaisService';
import type { Edital } from '@/services/types';

vi.mock('@/services/editaisService', () => ({
  getEditais: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    usuario: null,
    autenticado: false,
    logout: vi.fn(),
  }),
}));

vi.mock('@/components/Footer', () => ({
  default: () => <footer>Rodape</footer>,
}));

vi.mock('@/components/Hero', () => ({
  default: () => <section>Hero</section>,
}));

function criarEditais(qtd: number): Edital[] {
  return Array.from({ length: qtd }, (_, index) => ({
    id: String(index + 1),
    titulo: `Edital ${index + 1}`,
    unidade: index % 2 === 0 ? 'Darcy Ribeiro' : 'Gama',
    categoria: index % 2 === 0 ? 'Pesquisa' : 'Estágio',
    dataPublicacao: '2026-10-01',
    prazoFinal: '2026-12-31',
    status: 'aberto',
    descricao: `Descrição do edital ${index + 1}`,
    urlDocumento: 'https://example.com/edital.pdf',
  }));
}

describe('HomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renderiza apenas 12 cards na primeira página e navega para a segunda', async () => {
    vi.mocked(getEditais).mockResolvedValue(criarEditais(25));

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('Edital 1');
    const cards = document.querySelectorAll('.edital-card');
    expect(cards).toHaveLength(12);
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Próxima página' }));

    expect(await screen.findByText('Edital 13')).toBeInTheDocument();
    expect(screen.getByText('Página 2 de 3')).toBeInTheDocument();
  });

  it('reinicia a paginação ao aplicar uma busca', async () => {
    vi.mocked(getEditais).mockResolvedValue(criarEditais(25));

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('Edital 1');
    fireEvent.click(screen.getByRole('button', { name: 'Próxima página' }));
    fireEvent.change(
      screen.getByRole('searchbox', { name: 'Buscar editais' }),
      { target: { value: 'Edital 20' } },
    );

    expect(await screen.findByText('Edital 20')).toBeInTheDocument();
    expect(screen.queryByText('Edital 13')).not.toBeInTheDocument();
  });

  it('exibe estado vazio quando nenhum edital corresponde', async () => {
    vi.mocked(getEditais).mockResolvedValue(criarEditais(3));

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('Edital 1');
    fireEvent.change(
      screen.getByRole('searchbox', { name: 'Buscar editais' }),
      { target: { value: 'termo inexistente' } },
    );

    expect(await screen.findByText('Nenhum edital encontrado')).toBeInTheDocument();
  });
});
