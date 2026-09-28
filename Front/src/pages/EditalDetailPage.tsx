import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getEditalById } from '@/services/editaisService';
import type { Edital } from '@/services/types';
import { categoryBadgeStyle, formatDate } from '@/utils/editalDisplay';

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

  if (loading) return <p className="status-message">Carregando edital...</p>;
  if (error) return <p className="status-message">Erro ao carregar edital: {error}</p>;
  if (!edital) return <p className="status-message">Edital não encontrado.</p>;

  return (
    <main className="detail-page">
      <a className="detail-back-link" href="/">
        Voltar para editais
      </a>
      <article className="detail-card">
        <div className="badge-group">
          {edital.categoria && (
            <span className="badge" style={categoryBadgeStyle(edital.categoria)}>
              {edital.categoria}
            </span>
          )}
          <span className="badge badge-campus">{edital.unidade}</span>
        </div>
        <h1>{edital.titulo}</h1>
        <p className="detail-description">{edital.descricao}</p>
        <dl className="detail-metadata">
          <div>
            <dt>Publicação</dt>
            <dd>{formatDate(edital.dataPublicacao)}</dd>
          </div>
          <div>
            <dt>Prazo final</dt>
            <dd>{formatDate(edital.prazoFinal)}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{edital.status === 'aberto' ? 'Inscrições abertas' : 'Encerrado'}</dd>
          </div>
        </dl>
        <a className="detail-document-link" href={edital.urlDocumento} target="_blank" rel="noreferrer">
          Ver documento oficial
        </a>
      </article>
    </main>
  );
}
