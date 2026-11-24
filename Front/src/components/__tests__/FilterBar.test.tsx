import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import FilterBar from '../FilterBar';

describe('FilterBar', () => {
  it('indica o filtro ativo e limpa todos os filtros', () => {
    const onSelectCategoria = vi.fn();
    const onClearFilters = vi.fn();
    const onSelectStatus = vi.fn();

    render(
      <FilterBar
        areaCounts={[{ area: 'Darcy Ribeiro', count: 20 }]}
        activeCategoria="Pesquisa"
        activeStatus={null}
        onSelectCategoria={onSelectCategoria}
        onSelectStatus={onSelectStatus}
        onClearFilters={onClearFilters}
      />,
    );

    expect(screen.getByRole('button', { name: 'Pesquisa' })).toHaveClass('active');
    fireEvent.click(screen.getByRole('button', { name: 'Limpar filtros' }));
    expect(onClearFilters).toHaveBeenCalledOnce();
  });

  it('permite filtrar por campus e ano de publicação', () => {
    const onSelectCampus = vi.fn();
    const onSelectAno = vi.fn();

    render(
      <FilterBar
        areaCounts={[]}
        activeCategoria={null}
        activeStatus={null}
        activeCampus={null}
        activeAno={null}
        onSelectCategoria={vi.fn()}
        onSelectStatus={vi.fn()}
        onSelectCampus={onSelectCampus}
        onSelectAno={onSelectAno}
        onClearFilters={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Campus'), { target: { value: 'FGA (Gama)' } });
    expect(onSelectCampus).toHaveBeenCalledWith('FGA (Gama)');

    fireEvent.change(screen.getByLabelText('Ano'), { target: { value: '2026' } });
    expect(onSelectAno).toHaveBeenCalledWith(2026);
  });

  it('oferece o próximo ano no seletor de Ano para editais futuros', () => {
    const proximoAno = new Date().getFullYear() + 1;
    const onSelectAno = vi.fn();

    render(
      <FilterBar
        areaCounts={[]}
        activeCategoria={null}
        activeStatus={null}
        activeCampus={null}
        activeAno={null}
        onSelectCategoria={vi.fn()}
        onSelectStatus={vi.fn()}
        onSelectCampus={vi.fn()}
        onSelectAno={onSelectAno}
        onClearFilters={vi.fn()}
      />,
    );

    expect(screen.getByRole('option', { name: String(proximoAno) })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Ano'), { target: { value: String(proximoAno) } });
    expect(onSelectAno).toHaveBeenCalledWith(proximoAno);
  });
});
