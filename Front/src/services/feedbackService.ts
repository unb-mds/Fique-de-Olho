const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

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
  const response = await fetch(`${API_BASE_URL}/api/v1/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tipo: payload.tipo,
      mensagem: payload.mensagem.trim(),
      email: payload.email?.trim() || undefined,
      pagina: payload.pagina || (typeof window !== 'undefined' ? window.location.pathname : undefined),
    }),
  });

  if (!response.ok) {
    let detalhe = 'Não foi possível enviar seu feedback agora. Tente novamente em instantes.';
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') {
        detalhe = body.detail;
      }
    } catch {
      // mantém mensagem amigável padrão
    }
    throw new Error(detalhe);
  }

  return response.json();
}
