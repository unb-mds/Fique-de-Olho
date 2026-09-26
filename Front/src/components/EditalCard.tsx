import type { Edital } from '@/services/types';
import { categoryBadgeStyle, daysUntil, formatDate } from '@/utils/editalDisplay';

interface EditalCardProps {
  edital: Edital;
}

export default function EditalCard({ edital }: EditalCardProps) {
  const restantes = daysUntil(edital.prazoFinal);
  const urgente = restantes !== null && restantes >= 0 && restantes <= 7;

  // Ainda não navega para uma página de detalhe — essa rota/tela fica
  // para outra pessoa do time implementar quando o backend expuser o endpoint.
  return (
    <article className="edital-card">
      <div className="edital-card-badges">
        <div className="badge-group">
          {edital.categoria && (
            <span className="badge" style={categoryBadgeStyle(edital.categoria)}>
              {edital.categoria}
            </span>
          )}
          {edital.unidade && <span className="badge badge-campus">{edital.unidade}</span>}
        </div>
        <svg
          className="card-star"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="m12 3 2.6 5.9 6.4.6-4.8 4.3 1.4 6.3L12 16.9l-5.6 3.2 1.4-6.3-4.8-4.3 6.4-.6L12 3Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <h3 className="edital-card-title">{edital.titulo}</h3>
      <p className="edital-card-desc">{edital.descricao}</p>

      <div className="edital-card-footer">
        {urgente ? (
          <span className="badge badge-urgent">{restantes}d restantes</span>
        ) : (
          <span>até {formatDate(edital.prazoFinal)}</span>
        )}
        <div className="edital-card-footer-right">
          {edital.vagas !== undefined && <span>{edital.vagas} vagas</span>}
          {edital.valor && <span className="edital-card-valor">{edital.valor}</span>}
        </div>
      </div>
    </article>
  );
}
