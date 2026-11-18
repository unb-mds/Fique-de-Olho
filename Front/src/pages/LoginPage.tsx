import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { login, updateEmailPreference } from "@/services/authService";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { favoritarEdital } from "@/services/favoritosService";
import NotificationPreferenceDialog from "@/components/NotificationPreferenceDialog";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [exibirPreferencia, setExibirPreferencia] = useState(false);
  const [salvandoPreferencia, setSalvandoPreferencia] = useState(false);
  const [erroPreferencia, setErroPreferencia] = useState("");
  const location = useLocation();
  const loginState = location.state as
    | { fromFavorite?: boolean; returnTo?: string; pendingEditalId?: string }
    | null;
  const pendingEditalId = loginState?.pendingEditalId;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setErro("");
    setCarregando(true);

    try {
      const data = await login(email, senha);

      localStorage.setItem("token", data.access_token);
      localStorage.setItem("usuario", JSON.stringify(data.usuario));

      setExibirPreferencia(true);
    } catch {
      setErro("E-mail ou senha inválidos.");
    } finally {
      setCarregando(false);
    }
  }

  async function definirPreferencia(receberEmails: boolean) {
    setSalvandoPreferencia(true);
    setErroPreferencia("");

    try {
      const usuarioAtualizado = await updateEmailPreference(receberEmails);
      localStorage.setItem("usuario", JSON.stringify(usuarioAtualizado));
      if (pendingEditalId) {
        await favoritarEdital(pendingEditalId);
      }
      if (usuarioAtualizado.id) {
        sessionStorage.setItem(
          `notification-preference:${usuarioAtualizado.id}`,
          'chosen',
        );
      }
      window.location.href = "/";
    } catch {
      setErroPreferencia(
        "Não foi possível salvar sua escolha. Tente novamente.",
      );
    } finally {
      setSalvandoPreferencia(false);
    }
  }

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
          <p className="eyebrow">{loginState?.fromFavorite ? 'Salve esta oportunidade' : 'Sua área'}</p>
          <h1>{loginState?.fromFavorite ? 'Crie sua lista de editais' : 'Bem-vindo de volta'}</h1>
          <p>
            {loginState?.fromFavorite
              ? 'Entre ou crie uma conta para favoritar e acompanhar este edital.'
              : 'Entre para acessar seus editais favoritos.'}
          </p>
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
              setExibirPreferencia(true);
            }}
            onError={(msg) => setErro(msg)}
          />
        </div>

        <p className="login-card-footer">
          Ainda não tem uma conta? <Link to="/register">Criar conta</Link>
        </p>
      </section>

      <NotificationPreferenceDialog
        open={exibirPreferencia}
        saving={salvandoPreferencia}
        error={erroPreferencia}
        onChoose={definirPreferencia}
      />
    </main>
  );
}
