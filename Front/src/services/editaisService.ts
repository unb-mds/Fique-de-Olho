import { ApiError, apiRequest } from '@/services/apiClient';
import type { Edital } from './types';

const CACHE_TTL_MS = 120_000; // 2 minutos em memória para navegação instantânea
const MAX_CACHE_ENTRIES = 100;

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
let ultimaAtualizacaoCache: CacheItem<string | null> | null = null;


function setBoundedCache<T>(cache: Map<string, CacheItem<T>>, key: string, data: T): void {
  if (cache.has(key)) {
    cache.delete(key);
  } else if (cache.size >= MAX_CACHE_ENTRIES) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey !== undefined) {
      cache.delete(oldestKey);
    }
  }
  cache.set(key, { timestamp: Date.now(), data });
}

export function limparCacheEditais(): void {
  listCache.clear();
  listInflight.clear();
  detailCache.clear();
  detailInflight.clear();
  statsCache = null;
  statsInflight = null;
  ultimaAtualizacaoCache = null;
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

  let request: Promise<Edital[]> | undefined = undefined;
  request = (async () => {
    try {
      const dados = await apiRequest<Edital[]>(
        `/api/v1/editais/${query ? `?${query}` : ''}`,
        {
          method: 'GET',
          signal: params.signal,
          errorMessage: 'Erro ao buscar editais.',
        },
      );
      if (!Array.isArray(dados)) {
        throw new ApiError('Resposta inválida ao buscar editais.', { isTransient: true });
      }
      setBoundedCache(listCache, query, dados);
      return dados;
    } finally {
      if (!params.signal && listInflight.get(query) === request) {
        listInflight.delete(query);
      }
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

  let request: Promise<EditaisStats> | undefined = undefined;
  request = (async () => {
    try {
      const dados = await apiRequest<EditaisStats>('/api/v1/editais/stats', {
        method: 'GET',
        errorMessage: 'Erro ao buscar estatísticas.',
      });
      statsCache = { timestamp: Date.now(), data: dados };
      return dados;
    } finally {
      if (statsInflight === request) {
        statsInflight = null;
      }
    }
  })();

  statsInflight = request;
  return request;
}

/** Data/hora ISO da última atualização do catálogo, ou null se ainda não houver. */
export async function getUltimaAtualizacao(): Promise<string | null> {
  if (ultimaAtualizacaoCache && Date.now() - ultimaAtualizacaoCache.timestamp < CACHE_TTL_MS) {
    return ultimaAtualizacaoCache.data;
  }
  const dados = await apiRequest<{ ultima_atualizacao: string | null }>(
    '/api/v1/editais/ultima-atualizacao',
    {
      method: 'GET',
      errorMessage: 'Erro ao buscar a última atualização.',
    },
  );
  const valor = dados?.ultima_atualizacao ?? null;
  ultimaAtualizacaoCache = { timestamp: Date.now(), data: valor };
  return valor;
}

export async function getEditalById(id: string): Promise<Edital> {
  const key = String(id);
  const cached = detailCache.get(key);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data;
  }

  const inflight = detailInflight.get(key);
  if (inflight) return inflight;

  let request: Promise<Edital> | undefined = undefined;
  request = (async () => {
    try {
      const dados = await apiRequest<Edital>(`/api/v1/editais/${key}`, {
        method: 'GET',
        errorMessage: `Erro ao buscar edital ${key}.`,
      });
      setBoundedCache(detailCache, key, dados);
      return dados;
    } finally {
      if (detailInflight.get(key) === request) {
        detailInflight.delete(key);
      }
    }
  })();

  detailInflight.set(key, request);
  return request;
}
