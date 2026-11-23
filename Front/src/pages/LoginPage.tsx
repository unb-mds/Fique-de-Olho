import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ApiError, isTransientError } from "@/services/apiClient";
import { login } from "@/services/authService";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { favoritarEdital } from "@/services/favoritosService";
import { ativarAlertaEdital } from "@/services/notificacoesService";
import { salvarSessaoStorage } from "@/utils/authStorage";

type LoginLocationState = {
  fromFavorite?: boolean;
  fromAlert?: boolean;
  returnTo?: string;
  pendingEditalId?: string;
  pendingAlertEditalId?: string;
} | null;

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const location = useLocation();
  const loginState = location.state as LoginLocationState;
  const pendingEditalId = loginState?.pendingEditalId;
  const pendingAlertEditalId = loginState?.pendingAlertEditalId;

  async function finalizarPosLogin() {
    try {
      if (pendingEditalId) {
        await favoritarEdital(pendingEditalId);
      }
      if (pendingAlertEditalId) {
        await ativarAlertaEdital(pendingAlertEditalId);
      }
    } catch {
      // Mesmo se a ação pendente falhar, conclui o login normalmente.
    }

    const returnTo = loginState?.returnTo;
    const destino =
      returnTo && /^\/(?![/\\])/.test(returnTo)
        ? returnTo
        : "/";
    window.location.href = destino;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setErro("");
    setCarregando(true);

    try {
      const data = await login(email, senha);

      salvarSessaoStorage(data.access_token, data.usuario);

      await finalizarPosLogin();
    } catch (err: unknown) {
      if (err instanceof Error && (isTransientError(err) || err instanceof ApiError)) {
        setErro(err.message);
      } else {
        setErro("E-mail ou senha inválidos.");
      }
    } finally {
      setCarregando(false);
    }
  }

  const eyebrow = loginState?.fromAlert
    ? "Receba alertas por e-mail"
    : loginState?.fromFavorite
      ? "Salve esta oportunidade"
      : "Sua área";

  const heading = loginState?.fromAlert
    ? "Ative alertas deste edital"
    : loginState?.fromFavorite
      ? "Crie sua lista de editais"
      : "Bem-vindo de volta";

  const subtitle = loginState?.fromAlert
    ? "Entre ou crie uma conta para ativar notificações por e-mail sobre atualizações e prazos deste edital."
    : loginState?.fromFavorite
      ? "Entre ou crie uma conta para favoritar e acompanhar este edital."
      : "Entre para acessar seus editais favoritos e alertas.";

  return (
    <main className="login-page">
      <Link className="page-back-link auth-back-link" to="/">
        ← Voltar para editais
      </Link>
      <section className="login-card">
        <div className="login-card-header">
          <Link className="brand" to="/">
            <span className="brand-mark" aria-hidden="true">U</span>
            <span className="brand-name">Fique de Olho</span>
          </Link>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{heading}</h1>
          <p>{subtitle}</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div>
            <label htmlFor="email">E-mail</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Digite seu e-mail"
              name="email"
              autoComplete="email"
              required
            />
          </div>

          <div>
            <label htmlFor="senha">Senha</label>
            <input
              id="senha"
              type="password"
              value={senha}
              onChange={(event) => setSenha(event.target.value)}
              placeholder="Digite sua senha"
              name="password"
              autoComplete="current-password"
              required
            />
          </div>

          {erro && <p className="form-error" role="alert">{erro}</p>}

          <button type="submit" disabled={carregando}>
            {carregando ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <div className="auth-divider"><span>ou</span></div>
        <div className="auth-google">
          <GoogleSignInButton
            onSuccess={() => {
              void finalizarPosLogin();
            }}
            onError={(msg) => setErro(msg)}
          />
        </div>

        <p className="login-card-footer">
          Ainda não tem uma conta? <Link to="/register">Criar conta</Link>
        </p>
      </section>
    </main>
  );
}
