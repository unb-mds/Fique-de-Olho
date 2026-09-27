export default function Header() {
  return (
    <header className="site-header">
      <div className="brand">
        <span className="brand-mark">UnB</span>
        <span className="brand-name">Portal de Editais</span>
      </div>

      {/* Busca ainda não implementada — fica para outra pessoa do time ligar isso à API. */}
      <label className="header-search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
          <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input type="text" placeholder="Buscar editais, áreas, campi..." disabled />
      </label>

      <div className="header-actions">
        <span className="header-link">Editais</span>
        <span className="header-avatar" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
            <path
              d="M4 20c0-4 3.6-6 8-6s8 2 8 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </span>
      </div>
    </header>
  );
}
