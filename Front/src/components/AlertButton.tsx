import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  ativarAlertaEdital,
  desativarAlertaEdital,
  listarAlertasEditais,
} from "../services/notificacoesService";

interface AlertButtonProps {
  editalId: string | number;
  initialAtivo?: boolean;
  onChange?: (editalId: string | number, ativo: boolean) => void;
}

function BellIcon({ filled }: { filled: boolean }) {
  if (filled) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          fill="currentColor"
          d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6v-5a7 7 0 0 0-5.5-6.84V3.5a1.5 1.5 0 0 0-3 0v.66A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z"
        />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <path
        d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M13.73 21a2 2 0 0 1-3.46 0"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function AlertButton({
  editalId,
  initialAtivo = false,
  onChange,
}: AlertButtonProps) {
  const [ativo, setAtivo] = useState(initialAtivo);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");

  const { autenticado } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let montado = true;

    async function verificarAlerta() {
      if (!autenticado) {
        if (montado) setAtivo(false);
        return;
      }

      if (initialAtivo) {
        if (montado) setAtivo(true);
        return;
      }

      try {
        const alertas = await listarAlertasEditais();
        if (!montado) return;
        const jaAtivo = alertas.some((id) => String(id) === String(editalId));
        setAtivo(jaAtivo);
      } catch {
        if (montado) {
          setErro("Não foi possível verificar os alertas.");
        }
      }
    }

    verificarAlerta();
    return () => {
      montado = false;
    };
  }, [autenticado, editalId, initialAtivo]);

  async function alternarAlerta() {
    if (!autenticado) {
      navigate("/login", {
        state: {
          fromAlert: true,
          returnTo: window.location.pathname,
          pendingAlertEditalId: String(editalId),
        },
      });
      return;
    }

    setErro("");
    setCarregando(true);

    try {
      if (ativo) {
        await desativarAlertaEdital(editalId);
        setAtivo(false);
        onChange?.(editalId, false);
      } else {
        await ativarAlertaEdital(editalId);
        setAtivo(true);
        onChange?.(editalId, true);
      }
    } catch {
      setErro("Não foi possível atualizar a notificação por e-mail.");
    } finally {
      setCarregando(false);
    }
  }

  const label = ativo
    ? "Desativar notificações por e-mail deste edital"
    : "Ativar notificações por e-mail deste edital";

  return (
    <>
      <button
        type="button"
        className={`alert-button${ativo ? " alert-button--active" : ""}`}
        data-edital-id={editalId}
        onClick={alternarAlerta}
        disabled={carregando}
        aria-pressed={ativo}
        aria-label={label}
        title={
          ativo
            ? "Alertas por e-mail ativados — clique para desativar"
            : "Receber alertas por e-mail sobre atualizações e prazos deste edital"
        }
      >
        <BellIcon filled={ativo} />
      </button>

      {erro && (
        <span className="favorite-error" role="alert">
          {erro}
        </span>
      )}
    </>
  );
}
