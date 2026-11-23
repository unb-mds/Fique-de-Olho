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
          <div className="not-found-copy">
            <h1>Página não encontrada</h1>
            <p>
              Este endereço não existe ou mudou de lugar no portal. Volte para a
              listagem e explore os editais abertos da UnB.
            </p>
            <div className="not-found-actions">
              <Link className="button button-accent" to="/">
                Voltar para editais
              </Link>
            </div>
          </div>
          <div className="not-found-visual" aria-hidden="true">
            <span className="not-found-spark not-found-spark-one">✦</span>
            <div className="not-found-code">
              <span>4</span>
              <span className="not-found-eye-frame">
                <img src="/assets/af98f.svg" alt="" width="376" height="376" />
              </span>
              <span>4</span>
            </div>
            <span className="not-found-spark not-found-spark-two">✦</span>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
