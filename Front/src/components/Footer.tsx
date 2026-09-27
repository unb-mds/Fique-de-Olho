const CAMPI = ['Darcy Ribeiro', 'Gama', 'Ceilândia', 'Planaltina'];

export default function Footer() {
  const ano = new Date().getFullYear();

  return (
    <footer className="site-footer">
      <div className="footer-brand">
        <div className="brand">
          <span className="brand-mark">UnB</span>
          <span className="brand-name">Portal de Editais UnB</span>
        </div>
        <p className="footer-tagline">
          Universidade de Brasília — Diretoria de Desenvolvimento Acadêmico
        </p>
      </div>

      <div className="footer-meta">
        <span className="footer-copyright">© {ano} Universidade de Brasília</span>
        <div className="footer-campi">
          {CAMPI.map((campus, i) => (
            <span key={campus}>
              {i > 0 && <span className="footer-dot">·</span>}
              <span>{campus}</span>
            </span>
          ))}
        </div>
      </div>
    </footer>
  );
}
