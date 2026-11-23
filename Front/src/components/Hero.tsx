import type { Edital } from '@/services/types';
import { daysUntil, formatDate } from '@/utils/editalDisplay';
import { Link } from 'react-router-dom';
import FollowingEyes from './FollowingEyes';

interface HeroProps {
  editaisAbertos: Edital[];
  totalAbertos?: number;
}

export default function Hero({ editaisAbertos, totalAbertos }: HeroProps) {
  const safeEditais = Array.isArray(editaisAbertos) ? editaisAbertos : [];
  const destaques = safeEditais.slice(0, 3);

  return (
    <section className="hero">
      <div className="hero-cover">
        <div className="hero-copy">
          <p className="eyebrow">Oportunidades da UnB, sem complicação</p>
          <h1 className="hero-heading">Encontre o próximo passo da sua trajetória.</h1>
          <p className="hero-subtitle">
            Bolsas, pesquisa, estágios e projetos de extensão reunidos em um só lugar,
            com prazos e informações que você encontra rápido.
          </p>
          <div className="hero-actions">
            <a className="button button-accent" href="#editais">
              Explorar editais <span aria-hidden="true">↘</span>
            </a>
            <span className="hero-count">
              <strong>{totalAbertos ?? safeEditais.length}</strong>
              oportunidades abertas
            </span>
          </div>
        </div>

        <div className="hero-art">
          <FollowingEyes />
        </div>
      </div>

      {destaques.length > 0 && (
        <div className="hero-highlights" aria-label="Editais em destaque">
          {destaques.map((edital) => {
            const restantes = daysUntil(edital.prazoFinal);
            const urgente = restantes !== null && restantes >= 0 && restantes <= 7;
            return (
              <article key={edital.id} className="highlight-card">
                <div className="highlight-card-top">
                  {edital.categoria && (
                    <span className="badge badge-highlight">{edital.categoria}</span>
                  )}
                  {edital.vagas !== undefined && edital.vagas !== null && (
                    <span className="highlight-vagas">{edital.vagas} vagas</span>
                  )}
                </div>
                <h2 className="highlight-title">
                  <Link to={`/editais/${edital.id}`}>{edital.titulo}</Link>
                </h2>
                {edital.valor && <span className="highlight-valor">{edital.valor}</span>}
                <span className="highlight-prazo">
                  {urgente ? `${restantes}d restantes` : `Prazo: ${formatDate(edital.prazoFinal)}`}
                </span>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
