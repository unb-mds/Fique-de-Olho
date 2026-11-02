import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import EditalCard from '../EditalCard';
import type { Edital } from '@/services/types';

describe('EditalCard Component', () => {
  const mockEdital: Edital = {
    id: 'edital-123',
    titulo: 'Edital de Monitoria - Departamento de Ciência da Computação',
    unidade: 'Campus Darcy Ribeiro',
    categoria: 'Monitoria',
    dataPublicacao: '2026-10-01',
    prazoFinal: '2026-12-31',
    status: 'aberto',
    descricao: 'Seleção de monitores remunerados e voluntários.',
    urlDocumento: 'https://exemplo.unb.br/edital.pdf',
    vagas: 5,
    valor: 'R$ 700,00',
  };

  it('deve renderizar os dados principais do edital', () => {
    render(
      <MemoryRouter>
        <EditalCard edital={mockEdital} />
      </MemoryRouter>
    );

    expect(screen.getByText('Edital de Monitoria - Departamento de Ciência da Computação')).toBeInTheDocument();
    expect(screen.getByText('Campus Darcy Ribeiro')).toBeInTheDocument();
    expect(screen.getByText('Monitoria')).toBeInTheDocument();
    expect(screen.getByText('Seleção de monitores remunerados e voluntários.')).toBeInTheDocument();
    expect(screen.getByText('5 vagas')).toBeInTheDocument();
    expect(screen.getByText('R$ 700,00')).toBeInTheDocument();
  });

  it('deve apontar o link de navegação para a rota correta do edital', () => {
    render(
      <MemoryRouter>
        <EditalCard edital={mockEdital} />
      </MemoryRouter>
    );

    const titleLink = screen.getByRole('link', { name: /Edital de Monitoria/i });
    expect(titleLink).toHaveAttribute('href', '/editais/edital-123');
  });
});

