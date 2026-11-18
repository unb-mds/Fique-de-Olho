import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import EditalCard from '@/components/EditalCard';
import Footer from '@/components/Footer';
import Header from '@/components/Header';
import { useAuth } from '@/contexts/AuthContext';
import { listarFavoritos } from '@/services/favoritosService';
import type { Edital } from '@/services/types';

export default function FavoritesPage() {
  const { usuario } = useAuth();
  const [favoritos, setFavoritos] = useState<Edital[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarFavoritos()
      .then(setFavoritos)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  function handleFavoriteChange(editalId: string | number, favorito: boolean) {
    if (!favorito) {
      setFavoritos((current) => current.filter((edital) => String(edital.id) !== String(editalId)));
    }
  }

  return (
    <div>
      <Header />
      <main className="favorites-page">
        <section className="favorites-intro">
          <div>
            <p className="eyebrow">Sua área</p>
            <h1>Seus editais favoritos</h1>
            <p>
              Olá, {usuario?.nome}. Acompanhe aqui as oportunidades que você salvou
              e consulte os detalhes antes do prazo.
            </p>
          </div>
          <div className="favorites-count" aria-label={`${favoritos.length} editais salvos`}>
            <strong>{favoritos.length}</strong>
            <span>editais salvos</span>
          </div>
        </section>

        {loading && <p className="status-message">Carregando seus favoritos...</p>}
        {error && (
          <p className="status-message" role="alert">
            Não foi possível carregar seus favoritos. Atualize a página e tente novamente.
          </p>
        )}

        {!loading && !error && favoritos.length === 0 && (
          <div className="favorites-empty">
            <span aria-hidden="true">☆</span>
            <h2>Você ainda não salvou editais</h2>
            <p>Explore as oportunidades e use a estrela para montar sua lista.</p>
            <Link className="button button-accent" to="/#editais">
              Explorar editais
            </Link>
          </div>
        )}

        {!loading && !error && favoritos.length > 0 && (
          <div className="edital-list favorites-list">
            {favoritos.map((edital) => (
              <EditalCard
                key={edital.id}
                edital={edital}
                favoriteInitially
                onFavoriteChange={handleFavoriteChange}
              />
            ))}
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
