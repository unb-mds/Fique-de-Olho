import { useState } from 'react';

export default function FavoriteButton() {
  const [favorito, setFavorito] = useState(false);

  function alterarFavorito(e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    setFavorito((prev) => !prev);
  }

  return (
    <button
      type="button"
      onClick={alterarFavorito}
      aria-label={favorito ? 'Desfavoritar edital' : 'Favoritar edital'}
      title={favorito ? 'Desfavoritar edital' : 'Favoritar edital'}
      style={{ color: favorito ? '#f59e0b' : 'inherit' }}
    >
      {favorito ? '★' : '☆'}
    </button>
  );
}