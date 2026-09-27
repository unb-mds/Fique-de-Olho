import type { Edital } from '@/services/types';
import { daysUntil, formatDate } from '@/utils/editalDisplay';

interface HeroProps {
  editaisAbertos: Edital[];
}

export default function Hero({ editaisAbertos }: HeroProps) {
  const destaques = editaisAbertos.slice(0, 3);

  return (
    <section className="hero">
      <p className="hero-eyebrow">Destaques</p>
      <div className="hero-heading-row">
        <div>
          <h1 className="hero-heading">Editais em Aberto</h1>
          <p className="hero-subtitle">
            Pesquisa, estágios, bolsas, extensão e vestibular em um só lugar
          </p>
        </div>
        <span className="hero-count-pill">{editaisAbertos.length} editais ativos</span>
      </div>

      {destaques.length > 0 && (
        <div className="hero-highlights">
          {destaques.map((edital) => {
            const restantes = daysUntil(edital.prazoFinal);
            const urgente = restantes !== null && restantes >= 0 && restantes <= 7;
            return (
              <article key={edital.id} className="highlight-card">
                <div className="highlight-card-top">
                  {edital.categoria && (
                    <span
                      className="badge"
                      style={{ backgroundColor: 'rgba(255,255,255,0.14)', color: '#fff' }}
                    >
                      {edital.categoria}
                    </span>
                  )}
                  {edital.vagas !== undefined && (
                    <span className="highlight-vagas">{edital.vagas} vagas</span>
                  )}
                </div>
                <p className="highlight-title">{edital.titulo}</p>
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
