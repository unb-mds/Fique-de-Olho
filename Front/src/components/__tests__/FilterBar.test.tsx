import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import FilterBar from '../FilterBar';

describe('FilterBar', () => {
  it('indica o filtro ativo e limpa todos os filtros', () => {
    const onSelectCategoria = vi.fn();
    const onClearFilters = vi.fn();

    render(
      <FilterBar
        areaCounts={[{ area: 'Darcy Ribeiro', count: 20 }]}
        activeCategoria="Pesquisa"
        onSelectCategoria={onSelectCategoria}
        onClearFilters={onClearFilters}
      />,
    );

    expect(screen.getByRole('button', { name: 'Pesquisa' })).toHaveClass('active');
    fireEvent.click(screen.getByRole('button', { name: 'Limpar filtros' }));
    expect(onClearFilters).toHaveBeenCalledOnce();
  });
});
