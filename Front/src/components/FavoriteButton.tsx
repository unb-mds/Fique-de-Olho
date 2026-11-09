import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  listarFavoritos,
  favoritarEdital,
  desfavoritarEdital,
} from "../services/favoritosService";

interface FavoriteButtonProps {
  editalId: string | number;
}

export default function FavoriteButton({ editalId }: FavoriteButtonProps) {
  const [favorito, setFavorito] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");

  const { autenticado } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    async function verificarFavorito() {
      if (!autenticado) {
        setFavorito(false);
        return;
      }

      try {
        const favoritos = await listarFavoritos();

        const jaFavoritado = favoritos.some(
          (edital) => String(edital.id) === String(editalId)
        );

        setFavorito(jaFavoritado);
      } catch {
        setErro("Não foi possível verificar os favoritos.");
      }
    }

    verificarFavorito();
  }, [autenticado, editalId]);

  async function alterarFavorito() {
    if (!autenticado) {
      navigate("/login");
      return;
    }

    setErro("");
    setCarregando(true);

    try {
      if (favorito) {
        await desfavoritarEdital(editalId);
        setFavorito(false);
      } else {
        await favoritarEdital(editalId);
        setFavorito(true);
      }
    } catch {
      setErro("Não foi possível atualizar o favorito.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <>
      <button
        type="button"
        data-edital-id={editalId}
        onClick={alterarFavorito}
        disabled={carregando}
        aria-label={favorito ? "Desfavoritar edital" : "Favoritar edital"}
        title={favorito ? "Desfavoritar edital" : "Favoritar edital"}
      >
        {favorito ? "★" : "☆"}
      </button>

      {erro && <span>{erro}</span>}
    </>
  );
}