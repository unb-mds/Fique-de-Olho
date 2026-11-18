import { KNOWN_CATEGORIES } from '@/utils/editalDisplay';

interface AreaCount {
  area: string;
  count: number;
}

interface FilterBarProps {
  areaCounts: AreaCount[];
  activeCategoria: string | null;
  onSelectCategoria: (categoria: string | null) => void;
  onClearFilters: () => void;
}

export default function FilterBar({
  areaCounts,
  activeCategoria,
  onSelectCategoria,
  onClearFilters,
}: FilterBarProps) {
  return (
    <section className="filters-section">
      {areaCounts.length > 0 && (
        <div className="area-filter">
          <p className="filters-label">Unidades com oportunidades</p>
          <div className="area-pills">
            {areaCounts.map(({ area, count }) => (
              <span key={area} className="area-pill">
                {area} <span>({count})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="type-filter">
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
        {(activeCategoria !== null || areaCounts.length > 0) && (
          <button className="clear-filters-button" type="button" onClick={onClearFilters}>
            Limpar filtros
          </button>
        )}
      </div>
    </section>
  );
}
