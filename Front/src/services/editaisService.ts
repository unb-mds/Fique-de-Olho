import type { Edital } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const EDITAIS_CACHE_TTL_MS = 60_000;

let editaisListCache: { data: Edital[]; timestamp: number } | null = null;
const editalByIdCache = new Map<string, { data: Edital; timestamp: number }>();

export async function getEditais(): Promise<Edital[]> {
  const now = Date.now();
  if (editaisListCache && now - editaisListCache.timestamp < EDITAIS_CACHE_TTL_MS) {
    return editaisListCache.data;
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/editais/`);
  if (!response.ok) {
    throw new Error(`Erro ao buscar editais: ${response.status}`);
  }
  const data: Edital[] = await response.json();
  const fetchedAt = Date.now();
  editaisListCache = { data, timestamp: fetchedAt };
  for (const item of data) {
    if (item && item.id !== undefined) {
      editalByIdCache.set(String(item.id), { data: item, timestamp: fetchedAt });
    }
  }
  return data;
}

export async function getEditalById(id: string): Promise<Edital> {
  const key = String(id);
  const now = Date.now();
  const cached = editalByIdCache.get(key);
  if (cached && now - cached.timestamp < EDITAIS_CACHE_TTL_MS) {
    return cached.data;
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/editais/${id}`);
  if (!response.ok) {
    throw new Error(`Erro ao buscar edital ${id}: ${response.status}`);
  }
  const data: Edital = await response.json();
  editalByIdCache.set(key, { data, timestamp: Date.now() });
  return data;
}
