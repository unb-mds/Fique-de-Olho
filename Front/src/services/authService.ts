import { ApiError, apiRequest, getAuthHeaders } from '@/services/apiClient';

export function getAuthenticatedHeaders(): HeadersInit {
  return getAuthHeaders();
}

export type Usuario = {
  id: number;
  nome: string;
  email: string;
  receber_emails: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  usuario: Usuario;
};

export async function login(email: string, senha: string): Promise<LoginResponse> {
  try {
    return await apiRequest<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email,
        senha,
      }),
      errorMessage: 'E-mail ou senha inválidos.',
    });
  } catch (err: unknown) {
    if (
      err instanceof ApiError &&
      !err.isTransient &&
      (err.status === 401 || err.status === 400)
    ) {
      throw new ApiError('E-mail ou senha inválidos.', {
        status: err.status,
        isTransient: false,
        detail: err.detail,
      });
    }
    throw err;
  }
}

export async function loginWithGoogle(credential: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/api/v1/auth/google', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      credential,
    }),
    errorMessage: 'Falha na autenticação com o Google.',
  });
}

export type RegisterResponse = {
  id: number;
  nome: string;
  email: string;
};

export async function register(
  nome: string,
  email: string,
  senha: string,
): Promise<RegisterResponse> {
  return apiRequest<RegisterResponse>('/api/v1/auth/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      nome,
      email,
      senha,
    }),
    errorMessage: 'Não foi possível realizar o cadastro.',
  });
}

export async function getCurrentUser(): Promise<Usuario> {
  return apiRequest<Usuario>('/api/v1/auth/me', {
    method: 'GET',
    auth: true,
    requireAuth: true,
    errorMessage: 'Sessão inválida ou expirada.',
  });
}

export async function updateEmailPreference(receberEmails: boolean): Promise<Usuario> {
  return apiRequest<Usuario>('/api/v1/auth/me/email-preferences', {
    method: 'PATCH',
    auth: true,
    requireAuth: true,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ receber_emails: receberEmails }),
    errorMessage: 'Não foi possível atualizar a preferência de emails.',
  });
}
