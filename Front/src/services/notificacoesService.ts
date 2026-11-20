import { getAuthenticatedHeaders } from "./authService";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Notificacao = {
  id: number;
  edital_id: number;
  edital_titulo: string;
  tipo: "edital_atualizado" | "prazo_encerrando";
  status: "pendente" | "enviada" | "falhou";
  criada_em: string;
  enviada_em: string | null;
};

export type AlertaEditalResponse = {
  message: string;
  edital_id: number;
  usuario_id: number;
  notificar_email: boolean;
  email_configurado?: boolean;
};

let cachedToken: string | null = null;
let cachedAlertIds: Set<string> | null = null;
let inflightAlertRequest: Promise<string[]> | null = null;

export function limparCacheAlertas(): void {
  cachedToken = null;
  cachedAlertIds = null;
  inflightAlertRequest = null;
}

export async function listarNotificacoes(): Promise<Notificacao[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/auth/me/notifications`,
    { headers: getAuthenticatedHeaders() },
  );

  if (!response.ok) {
    throw new Error("Não foi possível carregar o histórico de notificações.");
  }

  return response.json();
}

export async function listarAlertasEditais(): Promise<string[]> {
  const token = localStorage.getItem("token");
  if (!token) {
    limparCacheAlertas();
    return [];
  }

  if (cachedToken !== token) {
    cachedToken = token;
    cachedAlertIds = null;
    inflightAlertRequest = null;
  }

  if (cachedAlertIds !== null) {
    return Array.from(cachedAlertIds);
  }

  if (inflightAlertRequest) {
    return inflightAlertRequest;
  }

  inflightAlertRequest = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/editais/alertas`, {
        method: "GET",
        headers: getAuthenticatedHeaders(),
      });

      if (!response.ok) {
        throw new Error("Erro ao listar alertas de editais.");
      }

      const data: { edital_ids?: Array<string | number> } = await response.json();
      const ids = (data.edital_ids ?? []).map((id) => String(id));
      if (cachedToken === token) {
        cachedAlertIds = new Set(ids);
      }
      return ids;
    } finally {
      inflightAlertRequest = null;
    }
  })();

  return inflightAlertRequest;
}

export async function ativarAlertaEdital(
  editalId: string | number,
): Promise<AlertaEditalResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/editais/${editalId}/alertas`,
    {
      method: "POST",
      headers: getAuthenticatedHeaders(),
    },
  );

  if (!response.ok) {
    throw new Error("Erro ao ativar notificações por e-mail.");
  }

  const data: AlertaEditalResponse = await response.json();
  if (cachedAlertIds !== null) {
    cachedAlertIds.add(String(editalId));
  }
  return data;
}

export async function desativarAlertaEdital(
  editalId: string | number,
): Promise<AlertaEditalResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/editais/${editalId}/alertas`,
    {
      method: "DELETE",
      headers: getAuthenticatedHeaders(),
    },
  );

  if (!response.ok) {
    throw new Error("Erro ao desativar notificações por e-mail.");
  }

  const data: AlertaEditalResponse = await response.json();
  if (cachedAlertIds !== null) {
    cachedAlertIds.delete(String(editalId));
  }
  return data;
}
