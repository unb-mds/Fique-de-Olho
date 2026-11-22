import { useId } from 'react';
import { KNOWN_CAMPI, KNOWN_CATEGORIES, KNOWN_YEARS } from '@/utils/editalDisplay';

interface AreaCount {
  area: string;
  count: number;
}

interface FilterBarProps {
  areaCounts: AreaCount[];
  activeCategoria: string | null;
  activeStatus: 'aberto' | 'fechado' | null;
  activeCampus?: string | null;
  activeAno?: number | null;
  onSelectCategoria: (categoria: string | null) => void;
  onSelectStatus: (situacao: 'aberto' | 'fechado' | null) => void;
  onSelectCampus?: (campus: string | null) => void;
  onSelectAno?: (ano: number | null) => void;
  onClearFilters: () => void;
}

export default function FilterBar({
  areaCounts,
  activeCategoria,
  activeStatus,
  activeCampus = null,
  activeAno = null,
  onSelectCategoria,
  onSelectStatus,
  onSelectCampus,
  onSelectAno,
  onClearFilters,
}: FilterBarProps) {
  const campusSelectId = useId();
  const anoSelectId = useId();
  const hasAnyFilter =
    activeCategoria !== null ||
    activeStatus !== null ||
    activeCampus !== null ||
    activeAno !== null ||
    areaCounts.length > 0;

  return (
    <section className="filters-section">
      <div className="filters-top-row">
        <div className="status-filter">
          <p className="filters-label">Situação</p>
          <div className="status-tabs" aria-label="Filtros de situação">
            <button
              type="button"
              className={`status-tab ${activeStatus === null ? 'active' : ''}`}
              onClick={() => onSelectStatus(null)}
            >
              Todas
            </button>
            <button
              type="button"
              className={`status-tab ${activeStatus === 'aberto' ? 'active' : ''}`}
              onClick={() => onSelectStatus('aberto')}
            >
              Abertos
            </button>
            <button
              type="button"
              className={`status-tab ${activeStatus === 'fechado' ? 'active' : ''}`}
              onClick={() => onSelectStatus('fechado')}
            >
              Encerrados
            </button>
          </div>
        </div>

        <div className="filter-select-row">
          <div className="filter-select-group">
            <label className="filters-label" htmlFor={campusSelectId}>
              Campus
            </label>
            <select
              id={campusSelectId}
              className="filter-select"
              value={activeCampus ?? ''}
              onChange={(event) => onSelectCampus?.(event.target.value || null)}
            >
              <option value="">Todos os campi</option>
              {KNOWN_CAMPI.map((campus) => (
                <option key={campus} value={campus}>
                  {campus}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-select-group">
            <label className="filters-label" htmlFor={anoSelectId}>
              Ano
            </label>
            <select
              id={anoSelectId}
              className="filter-select"
              value={activeAno ?? ''}
              onChange={(event) =>
                onSelectAno?.(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">Todos os anos</option>
              {KNOWN_YEARS.map((ano) => (
                <option key={ano} value={ano}>
                  {ano}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="type-filter">
        <p className="filters-label">Categoria</p>
        <div className="type-tabs" aria-label="Filtros de categoria">
          <button
            type="button"
            className={`type-tab ${activeCategoria === null ? 'active' : ''}`}
            onClick={() => onSelectCategoria(null)}
          >
            Todos
          </button>
          {KNOWN_CATEGORIES.map((categoria) => (
            <button
              key={categoria}
              type="button"
              className={`type-tab ${activeCategoria === categoria ? 'active' : ''}`}
              onClick={() => onSelectCategoria(categoria)}
            >
              <span className="type-tab-dot" />
              {categoria}
            </button>
          ))}
        </div>
        {hasAnyFilter && (
          <button className="clear-filters-button" type="button" onClick={onClearFilters}>
            Limpar filtros
          </button>
        )}
      </div>
    </section>
  );
}
