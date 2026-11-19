import { KNOWN_CATEGORIES } from '@/utils/editalDisplay';

interface AreaCount {
  area: string;
  count: number;
}

interface FilterBarProps {
  areaCounts: AreaCount[];
  activeCategoria: string | null;
  activeStatus: 'aberto' | 'fechado' | null;
  onSelectCategoria: (categoria: string | null) => void;
  onSelectStatus: (situacao: 'aberto' | 'fechado' | null) => void;
  onClearFilters: () => void;
}

export default function FilterBar({
  areaCounts,
  activeCategoria,
  activeStatus,
  onSelectCategoria,
  onSelectStatus,
  onClearFilters,
}: FilterBarProps) {
  return (
    <section className="filters-section">
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
        {(activeCategoria !== null || activeStatus !== null || areaCounts.length > 0) && (
          <button className="clear-filters-button" type="button" onClick={onClearFilters}>
            Limpar filtros
          </button>
        )}
      </div>
    </section>
  );
}
