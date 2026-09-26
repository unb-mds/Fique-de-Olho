import { KNOWN_CATEGORIES } from '@/utils/editalDisplay';

interface AreaCount {
  area: string;
  count: number;
}

interface FilterBarProps {
  areaCounts: AreaCount[];
  activeCategoria: string | null;
  onSelectCategoria: (categoria: string | null) => void;
}

export default function FilterBar({
  areaCounts,
  activeCategoria,
  onSelectCategoria,
}: FilterBarProps) {
  return (
    <section className="filters-section">
      {areaCounts.length > 0 && (
        <>
          <p className="filters-label">Áreas em destaque</p>
          <div className="area-pills">
            {areaCounts.map(({ area, count }) => (
              <span key={area} className="area-pill">
                {area} <span>({count})</span>
              </span>
            ))}
          </div>
        </>
      )}

      <div className="type-tabs">
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
    </section>
  );
}
