import { apiRequest } from '@/services/apiClient';

export type TipoFeedback = 'sugestao' | 'problema' | 'elogio';

export interface FeedbackPayload {
  tipo: TipoFeedback;
  mensagem: string;
  email?: string;
  pagina?: string;
}

export interface FeedbackResponse {
  id: number;
  tipo: TipoFeedback;
  mensagem: string;
  email?: string | null;
  pagina?: string | null;
  criado_em: string;
  message: string;
}

export async function enviarFeedback(payload: FeedbackPayload): Promise<FeedbackResponse> {
  return apiRequest<FeedbackResponse>('/api/v1/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tipo: payload.tipo,
      mensagem: payload.mensagem.trim(),
      email: payload.email?.trim() || undefined,
      pagina:
        payload.pagina ||
        (typeof window !== 'undefined' ? window.location.pathname : undefined),
    }),
    errorMessage:
      'Não foi possível enviar seu feedback agora. Tente novamente em instantes.',
  });
}
