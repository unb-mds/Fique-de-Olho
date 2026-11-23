import { ApiError, apiRequest } from '@/services/apiClient';
import { obterTokenStorage } from '@/utils/authStorage';
import type { Edital } from './types';

let cachedToken: string | null = null;
let cachedFavoritos: Edital[] | null = null;
let inflightFavoritosRequest: Promise<Edital[]> | null = null;

export function limparCacheFavoritos(): void {
  cachedToken = null;
  cachedFavoritos = null;
  inflightFavoritosRequest = null;
}

export async function listarFavoritos(): Promise<Edital[]> {
  const token = obterTokenStorage();
  if (!token) {
    limparCacheFavoritos();
    return [];
  }

  if (cachedToken !== token) {
    cachedToken = token;
    cachedFavoritos = null;
    inflightFavoritosRequest = null;
  }

  if (cachedFavoritos !== null) {
    return cachedFavoritos;
  }

  if (inflightFavoritosRequest) {
    return inflightFavoritosRequest;
  }

  let request: Promise<Edital[]> | undefined = undefined;
  request = (async () => {
    try {
      const dados = await apiRequest<Edital[]>('/api/v1/editais/favoritos', {
        method: 'GET',
        auth: true,
        errorMessage: 'Erro ao listar favoritos.',
      });

      if (!Array.isArray(dados)) {
        throw new ApiError('Resposta inválida ao listar favoritos.', { isTransient: true });
      }

      if (cachedToken === token) {
        cachedFavoritos = dados;
      }
      return dados;
    } finally {
      if (inflightFavoritosRequest === request) {
        inflightFavoritosRequest = null;
      }
    }
  })();

  inflightFavoritosRequest = request;
  return request;
}

export async function favoritarEdital(editalId: string | number): Promise<void> {
  await apiRequest<void>(`/api/v1/editais/${editalId}/favoritar`, {
    method: 'POST',
    auth: true,
    requireAuth: true,
    parseResponse: 'void',
    errorMessage: 'Erro ao favoritar edital.',
  });

  cachedFavoritos = null;
}

export async function desfavoritarEdital(editalId: string | number): Promise<void> {
  await apiRequest<void>(`/api/v1/editais/${editalId}/favoritar`, {
    method: 'DELETE',
    auth: true,
    requireAuth: true,
    parseResponse: 'void',
    errorMessage: 'Erro ao desfavoritar edital.',
  });

  if (cachedFavoritos !== null) {
    cachedFavoritos = cachedFavoritos.filter(
      (edital) => String(edital.id) !== String(editalId),
    );
  }
}
