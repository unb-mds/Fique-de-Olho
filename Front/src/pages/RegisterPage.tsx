import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "@/services/authService";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";

export default function RegisterPage() {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setErro("");
    setCarregando(true);

    try {
      await register(nome, email, senha);

      navigate("/login");
    } catch {
      setErro("Não foi possível realizar o cadastro.");
    } finally {
      setCarregando(false);
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
          <p className="eyebrow">Nova conta</p>
          <h1>Comece a acompanhar editais</h1>
          <p>Crie seu perfil para salvar oportunidades e montar sua lista.</p>
        </div>

        <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="nome">Nome</label>
          <input
            id="nome"
            type="text"
            value={nome}
            onChange={(event) => setNome(event.target.value)}
            placeholder="Digite seu nome"
            required
          />
        </div>

        <div>
          <label htmlFor="email">E-mail</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Digite seu e-mail"
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
            required
          />
        </div>

        {erro && <p>{erro}</p>}

        <button type="submit" disabled={carregando}>
          {carregando ? "Cadastrando..." : "Cadastrar"}
        </button>
      </form>

      <div className="auth-divider">
        <span>ou</span>
      </div>

      <div className="auth-google">
        <GoogleSignInButton
          text="signup_with"
          onError={(msg) => setErro(msg)}
        />
      </div>
      <p className="login-card-footer">
        Já tem uma conta? <Link to="/login">Entrar</Link>
      </p>
      </section>
    </main>
  );
}