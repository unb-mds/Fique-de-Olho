import { useEffect, useMemo, useState } from 'react';
import Header from '@/components/Header';
import Hero from '@/components/Hero';
import FilterBar from '@/components/FilterBar';
import EditalCard from '@/components/EditalCard';
import Footer from '@/components/Footer';
import { getEditais } from '@/services/editaisService';
import type { Edital } from '@/services/types';

export default function HomePage() {
  const [editais, setEditais] = useState<Edital[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoria, setCategoria] = useState<string | null>(null);

  useEffect(() => {
    getEditais()
      .then(setEditais)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const editaisAbertos = useMemo(
    () => editais.filter((e) => e.status === 'aberto'),
    [editais],
  );

  // "Área" ainda não existe como campo próprio na API — por ora, contamos
  // quantos editais abertos existem por unidade, só para dar visão geral.
  const areaCounts = useMemo(() => {
    const counts = new Map<string, number>();
    editaisAbertos.forEach((e) => {
      if (!e.unidade) return;
      counts.set(e.unidade, (counts.get(e.unidade) ?? 0) + 1);
    });
    return Array.from(counts.entries()).map(([area, count]) => ({ area, count }));
  }, [editaisAbertos]);

  // A busca por texto (barra do Header) ainda não está ligada a nada —
  // fica para outra pessoa do time implementar.
  const filtrados = useMemo(() => {
    return editais.filter((e) => {
      return categoria === null || (e.categoria ?? '').toLowerCase() === categoria.toLowerCase();
    });
  }, [editais, categoria]);

  return (
    <div>
      <Header />
      <Hero editaisAbertos={editaisAbertos} />
      <FilterBar
        areaCounts={areaCounts}
        activeCategoria={categoria}
        onSelectCategoria={setCategoria}
      />

      {loading && <p className="status-message">Carregando editais...</p>}
      {error && <p className="status-message">Erro ao carregar editais: {error}</p>}

      {!loading && !error && (
        <>
          {filtrados.length === 0 ? (
            <p className="empty-state">Nenhum edital encontrado para esse filtro.</p>
          ) : (
            <div className="edital-list">
              {filtrados.map((edital) => (
                <EditalCard key={edital.id} edital={edital} />
              ))}
            </div>
          )}
        </>
      )}

      <Footer />
    </div>
  );
}
