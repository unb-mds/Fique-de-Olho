import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  listarFavoritos,
  favoritarEdital,
  desfavoritarEdital,
} from "../services/favoritosService";
import { updateEmailPreference } from "../services/authService";
import NotificationPreferenceDialog from "./NotificationPreferenceDialog";

interface FavoriteButtonProps {
  editalId: string | number;
  initialFavorito?: boolean;
  onChange?: (editalId: string | number, favorito: boolean) => void;
}

export default function FavoriteButton({
  editalId,
  initialFavorito = false,
  onChange,
}: FavoriteButtonProps) {
  const [favorito, setFavorito] = useState(initialFavorito);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [exibirPreferencia, setExibirPreferencia] = useState(false);
  const [salvandoPreferencia, setSalvandoPreferencia] = useState(false);
  const [erroPreferencia, setErroPreferencia] = useState("");

  const { autenticado, usuario, atualizarUsuario } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    async function verificarFavorito() {
      if (!autenticado) {
        setFavorito(false);
        return;
      }

      if (initialFavorito) {
        setFavorito(true);
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
  }, [autenticado, editalId, initialFavorito]);

  async function alterarFavorito() {
    if (!autenticado) {
      navigate("/login", {
        state: {
          fromFavorite: true,
          returnTo: window.location.pathname,
          pendingEditalId: String(editalId),
        },
      });
      return;
    }

    setErro("");
    setCarregando(true);

    try {
      if (favorito) {
        await desfavoritarEdital(editalId);
        setFavorito(false);
        onChange?.(editalId, false);
      } else {
        await favoritarEdital(editalId);
        setFavorito(true);
        onChange?.(editalId, true);

        const preferenceKey =
          usuario ? `notification-preference:${usuario.id}` : null;
        if (preferenceKey && !sessionStorage.getItem(preferenceKey)) {
          setExibirPreferencia(true);
        }
      }

    } catch {
      setErro("Não foi possível atualizar o favorito.");
    } finally {
      setCarregando(false);
    }
  }

  async function definirPreferencia(receberEmails: boolean) {
    setSalvandoPreferencia(true);
    setErroPreferencia("");
    try {
      await updateEmailPreference(receberEmails);
      await atualizarUsuario();
      if (usuario) {
        sessionStorage.setItem(`notification-preference:${usuario.id}`, 'chosen');
      }
      setExibirPreferencia(false);
      navigate("/", { replace: true });
    } catch {
      setErroPreferencia("Não foi possível salvar sua escolha. Tente novamente.");
    } finally {
      setSalvandoPreferencia(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="favorite-button"
        data-edital-id={editalId}
        onClick={alterarFavorito}
        disabled={carregando}
        aria-label={favorito ? "Desfavoritar edital" : "Favoritar edital"}
        title={favorito ? "Desfavoritar edital" : "Favoritar edital"}
      >
        {favorito ? "★" : "☆"}
      </button>

      {erro && (
        <span className="favorite-error" role="alert">
          {erro}
        </span>
      )}
      <NotificationPreferenceDialog
        open={exibirPreferencia}
        saving={salvandoPreferencia}
        error={erroPreferencia}
        onChoose={definirPreferencia}
      />
    </>
  );
}
