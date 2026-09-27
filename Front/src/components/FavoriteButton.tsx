import { useState } from 'react';

export default function FavoriteButton() {
  const [favorito, setFavorito] = useState(false);
  const [mostrarLogin, setMostrarLogin] = useState(false);

  function alterarFavorito() {
    const usuarioLogado = false;

    if (!usuarioLogado) {
      setMostrarLogin(true);
      return;
    }

    setFavorito(!favorito);
  }

  return (
    <>
      <button
        type="button"
        onClick={alterarFavorito}
        aria-label={favorito ? 'Desfavoritar edital' : 'Favoritar edital'}
        title={favorito ? 'Desfavoritar edital' : 'Favoritar edital'}
      >
        {favorito ? '★' : '☆'}
      </button>

      {mostrarLogin && (
        <div>
          <p>Faça login para favoritar este edital.</p>

          <button
            type="button"
            onClick={() => setMostrarLogin(false)}
          >
            Fechar
          </button>
        </div>
      )}
    </>
  );
}