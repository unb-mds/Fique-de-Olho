import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import Header from '@/components/Header';

/**
 * Página exibida para rotas inexistentes, mantendo cabeçalho, navegação e rodapé.
 */
export default function NotFoundPage() {
  return (
    <div>
      <Header />
      <main className="not-found-page">
        <section className="not-found-card">
          <p className="eyebrow">Erro 404</p>
          <h1>Página não encontrada</h1>
          <p>
            O endereço acessado não existe ou foi movido. Volte para o portal para
            explorar os editais abertos da UnB.
          </p>
          <Link className="button button-accent" to="/">
            Voltar para editais
          </Link>
        </section>
      </main>
      <Footer />
    </div>
  );
}
