import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
export default function Header() {
  const { usuario, autenticado, logout } = useAuth();
  const navigate = useNavigate();

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

  {autenticado && usuario ? (
    <>
      <span className="header-link">{usuario.nome}</span>

      <button
        type="button"
        onClick={() => {
          logout();
          navigate("/login");
        }}
      >
        Sair
      </button>
    </>
  ) : (
    <button
      type="button"
      onClick={() => navigate("/login")}
    >
      Entrar
    </button>
  )}
</div>
    </header>
  );
}
