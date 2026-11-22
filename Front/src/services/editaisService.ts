import type { Edital } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const CACHE_TTL_MS = 120_000; // 2 minutos em memória para navegação instantânea

export interface GetEditaisParams {
  q?: string;
  categoria?: string | null;
  status?: 'aberto' | 'fechado' | null;
  campus?: string | null;
  ano?: number | null;
  skip?: number;
  limit?: number;
  signal?: AbortSignal;
}

export interface EditaisStats {
  total: number;
  abertos: number;
  encerrados: number;
}

interface CacheItem<T> {
  timestamp: number;
  data: T;
}

const listCache = new Map<string, CacheItem<Edital[]>>();
const listInflight = new Map<string, Promise<Edital[]>>();
const detailCache = new Map<string, CacheItem<Edital>>();
const detailInflight = new Map<string, Promise<Edital>>();
let statsCache: CacheItem<EditaisStats> | null = null;
let statsInflight: Promise<EditaisStats> | null = null;

export function limparCacheEditais(): void {
  listCache.clear();
  listInflight.clear();
  detailCache.clear();
  detailInflight.clear();
  statsCache = null;
  statsInflight = null;
}

export async function getEditais(params: GetEditaisParams = {}): Promise<Edital[]> {
  const searchParams = new URLSearchParams();
  if (params.q?.trim()) searchParams.set('q', params.q.trim());
  if (params.categoria) searchParams.set('categoria', params.categoria);
  if (params.status) searchParams.set('status', params.status);
  if (params.campus) searchParams.set('campus', params.campus);
  if (params.ano !== undefined && params.ano !== null) searchParams.set('ano', String(params.ano));
  if (params.skip !== undefined) searchParams.set('skip', String(params.skip));
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));

  const query = searchParams.toString();
  const cached = listCache.get(query);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data;
  }

  if (!params.signal) {
    const inflight = listInflight.get(query);
    if (inflight) return inflight;
  }

  const request = (async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/editais/${query ? `?${query}` : ''}`,
        params.signal ? { signal: params.signal } : undefined,
      );
      if (!response.ok) {
        throw new Error(`Erro ao buscar editais: ${response.status}`);
      }
      const dados: Edital[] = await response.json();
      listCache.set(query, { timestamp: Date.now(), data: dados });
      return dados;
    } finally {
      listInflight.delete(query);
    }
  })();

  if (!params.signal) {
    listInflight.set(query, request);
  }
  return request;
}

export async function getEditaisStats(): Promise<EditaisStats> {
  if (statsCache && Date.now() - statsCache.timestamp < CACHE_TTL_MS) {
    return statsCache.data;
  }
  if (statsInflight) return statsInflight;

  statsInflight = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/editais/stats`);
      if (!response.ok) {
        throw new Error(`Erro ao buscar estatísticas: ${response.status}`);
      }
      const dados: EditaisStats = await response.json();
      statsCache = { timestamp: Date.now(), data: dados };
      return dados;
    } finally {
      statsInflight = null;
    }
  })();

  return statsInflight;
}

export async function getEditalById(id: string): Promise<Edital> {
  const key = String(id);
  const cached = detailCache.get(key);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data;
  }

  const inflight = detailInflight.get(key);
  if (inflight) return inflight;

  const request = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/editais/${key}`);
      if (!response.ok) {
        throw new Error(`Erro ao buscar edital ${key}: ${response.status}`);
      }
      const dados: Edital = await response.json();
      detailCache.set(key, { timestamp: Date.now(), data: dados });
      return dados;
    } finally {
      detailInflight.delete(key);
    }
  })();

  detailInflight.set(key, request);
  return request;
}
