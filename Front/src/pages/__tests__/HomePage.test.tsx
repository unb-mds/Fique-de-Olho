import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HomePage from '../HomePage';
import { getEditais, getEditaisStats, getUltimaAtualizacao } from '@/services/editaisService';
import type { Edital } from '@/services/types';

vi.mock('@/services/editaisService', () => ({
  getEditais: vi.fn(),
  getEditaisStats: vi.fn(),
  getUltimaAtualizacao: vi.fn(),
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
    vi.mocked(getEditaisStats).mockResolvedValue({
      total: 25,
      abertos: 20,
      encerrados: 5,
    });
    vi.mocked(getUltimaAtualizacao).mockResolvedValue(null);
  });

  it('renderiza 12 cards iniciais e permite carregar mais', async () => {
    vi.mocked(getEditais).mockImplementation(async (params) => {
      if (params?.limit === 3) return criarEditais(3);
      if (params?.skip) return criarEditais(13).map((edital, index) => ({
        ...edital,
        id: String(index + 13),
        titulo: `Edital ${index + 13}`,
      }));
      return criarEditais(12);
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('Edital 1');
    const cards = document.querySelectorAll('.edital-card');
    expect(cards).toHaveLength(12);
    expect(screen.getByRole('button', { name: 'Carregar mais' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Carregar mais' }));

    expect(await screen.findByText('Edital 13')).toBeInTheDocument();
  });

  it('atualiza os resultados ao aplicar uma busca', async () => {
    vi.mocked(getEditais).mockImplementation(async (params) => {
      if (params?.limit === 3) return criarEditais(3);
      const dados = criarEditais(25);
      if (params?.q) return dados.filter((edital) => edital.titulo.includes(params.q as string));
      return dados.slice(0, 12);
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('Edital 1');
    fireEvent.change(
      screen.getByRole('searchbox', { name: 'Buscar editais' }),
      { target: { value: 'Edital 20' } },
    );

    expect(await screen.findByText('Edital 20')).toBeInTheDocument();
  });

  it('exibe estado vazio quando nenhum edital corresponde', async () => {
    vi.mocked(getEditais).mockImplementation(async (params) => {
      if (params?.limit === 3) return criarEditais(3);
      if (params?.q) return [];
      return criarEditais(3);
    });

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

  it('permite tentar novamente quando a carga inicial falha', async () => {
    let falhar = true;
    vi.mocked(getEditais).mockImplementation(async (params) => {
      if (params?.limit === 3) return criarEditais(3);
      if (falhar) throw new Error('Servidor indisponível');
      return criarEditais(2);
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const retryBtn = await screen.findByRole('button', { name: 'Tentar novamente' });
    falhar = false;
    fireEvent.click(retryBtn);

    expect(await screen.findByText('Edital 1')).toBeInTheDocument();
  });

  it('preserva editais já carregados quando carregarMais falha e permite tentar novamente', async () => {
    let falharPaginacao = true;
    vi.mocked(getEditais).mockImplementation(async (params) => {
      if (params?.limit === 3) return criarEditais(3);
      if (params?.skip) {
        if (falharPaginacao) throw new Error('Falha ao paginar editais');
        return criarEditais(1).map((e) => ({ ...e, id: '13', titulo: 'Edital 13' }));
      }
      return criarEditais(12);
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('Edital 1');
    fireEvent.click(screen.getByRole('button', { name: 'Carregar mais' }));

    expect(await screen.findByText('Falha ao paginar editais')).toBeInTheDocument();
    expect(screen.getByText('Edital 1')).toBeInTheDocument();

    falharPaginacao = false;
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));

    expect(await screen.findByText('Edital 13')).toBeInTheDocument();
  });
});
