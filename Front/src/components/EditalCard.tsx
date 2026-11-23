import type { Edital } from '@/services/types';
import { categoryBadgeStyle, daysUntil, formatDate } from '@/utils/editalDisplay';
import { Link } from 'react-router-dom';
import AlertButton from './AlertButton';
import FavoriteButton from './FavoriteButton';

interface EditalCardProps {
  edital: Edital;
  favoriteInitially?: boolean;
  onFavoriteChange?: (editalId: string | number, favorito: boolean) => void;
}

export default function EditalCard({
  edital,
  favoriteInitially = false,
  onFavoriteChange,
}: EditalCardProps) {
  const restantes = daysUntil(edital.prazoFinal);
  const urgente = restantes !== null && restantes >= 0 && restantes <= 7;
  const orgao = edital.orgaoEmissor || edital.orgao_emissor;

  return (
    <article className="edital-card">
      <div className="edital-card-actions">
        <AlertButton editalId={edital.id} />
        <FavoriteButton
          editalId={edital.id}
          initialFavorito={favoriteInitially}
          onChange={onFavoriteChange}
        />
      </div>
      <div className="edital-card-badges">
        <div className="badge-group">
          {edital.categoria && (
            <span className="badge" style={categoryBadgeStyle(edital.categoria)}>
              {edital.categoria}
            </span>
          )}
          {edital.unidade && <span className="badge badge-campus">{edital.unidade}</span>}
          {orgao && <span className="badge badge-orgao">{orgao}</span>}
        </div>
      </div>

      <h3 className="edital-card-title">
        <Link to={`/editais/${edital.id}`} title={edital.titulo}>
          {edital.titulo}
        </Link>
      </h3>
      <p className="edital-card-desc">{edital.descricao}</p>

      <div className="edital-card-footer">
        <div className="edital-meta">
          {urgente ? (
            <span className="badge badge-urgent">{restantes}d restantes</span>
          ) : (
            <span><strong>Prazo</strong> {formatDate(edital.prazoFinal)}</span>
          )}
          <div className="edital-card-footer-right">
            {edital.vagas !== undefined && edital.vagas !== null && (
              <span>{edital.vagas} vagas</span>
            )}
            {edital.valor && <span className="edital-card-valor">{edital.valor}</span>}
          </div>
        </div>
        <Link className="card-link" to={`/editais/${edital.id}`}>
          Ver edital <span aria-hidden="true">↗</span>
        </Link>
      </div>
    </article>
  );
}
