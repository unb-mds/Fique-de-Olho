import type { Edital } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export interface GetEditaisParams {
  q?: string;
  categoria?: string | null;
  status?: 'aberto' | 'fechado' | null;
  skip?: number;
  limit?: number;
}

export async function getEditais(params: GetEditaisParams = {}): Promise<Edital[]> {
  const searchParams = new URLSearchParams();
  if (params.q?.trim()) searchParams.set('q', params.q.trim());
  if (params.categoria) searchParams.set('categoria', params.categoria);
  if (params.status) searchParams.set('status', params.status);
  if (params.skip !== undefined) searchParams.set('skip', String(params.skip));
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));

  const query = searchParams.toString();
  const response = await fetch(`${API_BASE_URL}/api/v1/editais/${query ? `?${query}` : ''}`);
  if (!response.ok) {
    throw new Error(`Erro ao buscar editais: ${response.status}`);
  }
  return response.json();
}

export interface EditaisStats {
  total: number;
  abertos: number;
  encerrados: number;
}

export async function getEditaisStats(): Promise<EditaisStats> {
  const response = await fetch(`${API_BASE_URL}/api/v1/editais/stats`);
  if (!response.ok) {
    throw new Error(`Erro ao buscar estatísticas: ${response.status}`);
  }
  return response.json();
}

export async function getEditalById(id: string): Promise<Edital> {
  const response = await fetch(`${API_BASE_URL}/api/v1/editais/${id}`);
  if (!response.ok) {
    throw new Error(`Erro ao buscar edital ${id}: ${response.status}`);
  }
  return response.json();
}
