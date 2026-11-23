import { ApiError, apiRequest } from '@/services/apiClient';
import { obterTokenStorage } from '@/utils/authStorage';

export type Notificacao = {
  id: number;
  edital_id: number;
  edital_titulo: string;
  tipo: 'edital_atualizado' | 'prazo_encerrando';
  status: 'pendente' | 'enviada' | 'falhou';
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
  const dados = await apiRequest<Notificacao[]>('/api/v1/auth/me/notifications', {
    method: 'GET',
    auth: true,
    requireAuth: true,
    errorMessage: 'Não foi possível carregar o histórico de notificações.',
  });

  if (!Array.isArray(dados)) {
    throw new ApiError('Resposta inválida ao listar notificações.', { isTransient: true });
  }

  return dados;
}

export async function listarAlertasEditais(): Promise<string[]> {
  const token = obterTokenStorage();
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

  let request: Promise<string[]> | undefined = undefined;
  request = (async () => {
    try {
      const data = await apiRequest<{ edital_ids?: Array<string | number> }>(
        '/api/v1/editais/alertas',
        {
          method: 'GET',
          auth: true,
          errorMessage: 'Erro ao listar alertas de editais.',
        },
      );

      const ids = (data.edital_ids ?? []).map((id) => String(id));
      if (cachedToken === token) {
        cachedAlertIds = new Set(ids);
      }
      return ids;
    } finally {
      if (inflightAlertRequest === request) {
        inflightAlertRequest = null;
      }
    }
  })();

  inflightAlertRequest = request;
  return request;
}

export async function ativarAlertaEdital(
  editalId: string | number,
): Promise<AlertaEditalResponse> {
  const data = await apiRequest<AlertaEditalResponse>(
    `/api/v1/editais/${editalId}/alertas`,
    {
      method: 'POST',
      auth: true,
      requireAuth: true,
      errorMessage: 'Erro ao ativar notificações por e-mail.',
    },
  );

  if (cachedAlertIds !== null) {
    cachedAlertIds.add(String(editalId));
  }
  return data;
}

export async function desativarAlertaEdital(
  editalId: string | number,
): Promise<AlertaEditalResponse> {
  const data = await apiRequest<AlertaEditalResponse>(
    `/api/v1/editais/${editalId}/alertas`,
    {
      method: 'DELETE',
      auth: true,
      requireAuth: true,
      errorMessage: 'Erro ao desativar notificações por e-mail.',
    },
  );

  if (cachedAlertIds !== null) {
    cachedAlertIds.delete(String(editalId));
  }
  return data;
}
