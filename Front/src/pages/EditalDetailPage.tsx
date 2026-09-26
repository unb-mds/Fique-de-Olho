import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getEditalById } from '@/services/editaisService';
import type { Edital } from '@/services/types';

export default function EditalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [edital, setEdital] = useState<Edital | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getEditalById(id)
      .then(setEdital)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p>Carregando...</p>;
  if (error) return <p>Erro: {error}</p>;
  if (!edital) return <p>Edital não encontrado.</p>;

  return (
    <main>
      <h1>{edital.titulo}</h1>
      <p>{edital.unidade}</p>
      <p>{edital.descricao}</p>
      <a href={edital.urlDocumento} target="_blank" rel="noreferrer">
        Ver documento original
      </a>
    </main>
  );
}
