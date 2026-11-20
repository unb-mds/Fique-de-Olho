import type { Edital } from './types';

/**
 * Busca editais por título.
 *
 * Implementação atual (RF04 — fase local): filtra em memória a lista de
 * editais já carregada, sem nenhuma chamada de rede extra.
 *
 * Troca futura para API real: quando o backend expuser um endpoint de busca
 * (ex. `GET /api/v1/editais/?search=termo`), troque o corpo desta função por
 * um `fetch`/`await` que chama esse endpoint. A assinatura
 * `(editais, termo) => Edital[]` pode virar `(termo) => Promise<Edital[]>` —
 * só é preciso então ajustar o `useEffect`/estado em HomePage.tsx que chama
 * esta função, sem mexer em mais nada do restante do app.
 */
export function searchEditaisPorTitulo(editais: Edital[], termo: string): Edital[] {
  const termoNormalizado = termo.trim().toLowerCase();
  if (!termoNormalizado) return editais;
  return editais.filter((edital) => (edital.titulo ?? '').toLowerCase().includes(termoNormalizado));
}
