import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Header() {
  const { usuario, autenticado, logout } = useAuth();
  const navigate = useNavigate();

  const nomeUsuario =
    typeof usuario?.nome === 'string' && usuario.nome.trim().length > 0
      ? usuario.nome.trim()
      : 'Usuário';
  const inicialUsuario = nomeUsuario.charAt(0).toUpperCase();

  return (
    <header className="site-header">
      <Link className="brand" to="/" aria-label="Portal de Editais UnB — início">
        <span className="brand-mark" aria-hidden="true">U</span>
        <span className="brand-name">Fique de Olho</span>
      </Link>

      <nav className="primary-nav" aria-label="Navegação principal">
        <a href="/#editais">Editais</a>
        <a href="/#como-funciona">Como funciona</a>
      </nav>


     <div className="header-actions">
  {autenticado && usuario ? (
    <>
      <button
        className="user-profile-button"
        type="button"
        onClick={() => navigate("/favoritos")}
        aria-label={`Abrir perfil de ${nomeUsuario} e ver favoritos`}
      >
        <span className="profile-avatar" aria-hidden="true">
          {inicialUsuario}
        </span>
        <span className="profile-copy">
          <strong>{nomeUsuario}</strong>
          <small>Meus editais</small>
        </span>
      </button>

      <button
        className="button button-ghost"
        type="button"
        onClick={() => {
          logout();
          navigate("/", { replace: true });
        }}
      >
        Sair
      </button>
    </>
  ) : (
    <>
      <button type="button" onClick={() => navigate("/login")}>
        Entrar
      </button>
      <button className="button button-accent" type="button" onClick={() => navigate("/register")}>
        Criar conta
      </button>
    </>
  )}
</div>
    </header>
  );
}
