import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import Hero from '../Hero';

function renderHero(ultimaAtualizacao?: string | null) {
  return render(
    <MemoryRouter>
      <Hero editaisAbertos={[]} totalAbertos={0} ultimaAtualizacao={ultimaAtualizacao} />
    </MemoryRouter>,
  );
}

describe('Hero - selo de última atualização', () => {
  it('mostra data e hora no horário de Brasília', () => {
    // 19:36 UTC = 16:36 em Brasília (UTC-3)
    renderHero('2026-11-24T19:36:00Z');

    expect(screen.getByText(/Atualizado em/)).toBeInTheDocument();
    expect(screen.getByText('24/11/2026 às 16:36')).toBeInTheDocument();
  });

  it('não mostra o selo quando não há data', () => {
    renderHero(null);

    expect(screen.queryByText(/Atualizado em/)).not.toBeInTheDocument();
  });

  it('não mostra o selo quando a data é inválida', () => {
    renderHero('data-invalida');

    expect(screen.queryByText(/Atualizado em/)).not.toBeInTheDocument();
  });
});