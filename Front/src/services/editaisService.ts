import type { Edital } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export async function getEditais(): Promise<Edital[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/editais/`);
  if (!response.ok) {
    throw new Error(`Erro ao buscar editais: ${response.status}`);
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
