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
