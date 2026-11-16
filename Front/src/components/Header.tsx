import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

interface HeaderProps {
  searchValue?: string;
  onSearchChange?: (value: string) => void;
}

export default function Header({ searchValue, onSearchChange }: HeaderProps) {
  const {
    usuario,
    autenticado,
    atualizarPreferenciaEmail,
    logout,
  } = useAuth();
  const navigate = useNavigate();
  const [atualizandoPreferencia, setAtualizandoPreferencia] = useState(false);
  const [erroPreferencia, setErroPreferencia] = useState<string | null>(null);

  async function alternarPreferencia(receberEmails: boolean) {
    setAtualizandoPreferencia(true);
    setErroPreferencia(null);

    try {
      await atualizarPreferenciaEmail(receberEmails);
    } catch (error) {
      setErroPreferencia(
        error instanceof Error
          ? error.message
          : "Não foi possível atualizar a preferência.",
      );
    } finally {
      setAtualizandoPreferencia(false);
    }
  }

  return (
    <header className="site-header">
      <div className="brand">
        <span className="brand-mark">UnB</span>
        <span className="brand-name">Portal de Editais</span>
      </div>

      <label className="header-search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
          <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          type="text"
          placeholder="Buscar editais pelo título..."
          value={searchValue ?? ""}
          onChange={(event) => onSearchChange?.(event.target.value)}
        />
      </label>

      <div className="header-actions">
        <span className="header-link">Editais</span>

        {autenticado && usuario ? (
          <>
            <span className="header-link">{usuario.nome}</span>
            <button type="button" onClick={() => navigate("/notifications")}>
              Notificações
            </button>
            <label className="email-preference">
              <input
                type="checkbox"
                checked={usuario.receber_emails}
                disabled={atualizandoPreferencia}
                onChange={(event) => alternarPreferencia(event.target.checked)}
              />
              Receber emails
            </label>
            {erroPreferencia && (
              <span className="header-error" role="alert">
                {erroPreferencia}
              </span>
            )}
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
          <>
            <button type="button" onClick={() => navigate("/login")}>
              Entrar
            </button>
            <button type="button" onClick={() => navigate("/register")}>
              Criar conta
            </button>
          </>
        )}
      </div>
    </header>
  );
}
