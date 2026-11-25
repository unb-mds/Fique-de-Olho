import type { CSSProperties } from 'react';

// Mapeia cada categoria de edital para as cores de badge usadas no protótipo.
// Adicione novas categorias aqui conforme o backend passar a retorná-las.
const CATEGORY_STYLES: Record<string, { bgVar: string; fgVar: string }> = {
  vestibular: { bgVar: '--pill-vestibular-bg', fgVar: '--pill-vestibular-fg' },
  estagio: { bgVar: '--pill-estagio-bg', fgVar: '--pill-estagio-fg' },
  extensao: { bgVar: '--pill-extensao-bg', fgVar: '--pill-extensao-fg' },
  pesquisa: { bgVar: '--pill-pesquisa-bg', fgVar: '--pill-pesquisa-fg' },
  'pos-graduacao': { bgVar: '--pill-pesquisa-bg', fgVar: '--pill-pesquisa-fg' },
  graduacao: { bgVar: '--pill-vestibular-bg', fgVar: '--pill-vestibular-fg' },
  intercambio: { bgVar: '--pill-extensao-bg', fgVar: '--pill-extensao-fg' },
  evento: { bgVar: '--pill-extensao-bg', fgVar: '--pill-extensao-fg' },
  bolsa: { bgVar: '--pill-pesquisa-bg', fgVar: '--pill-pesquisa-fg' },
};

function normalizeCategoria(categoria: string | null | undefined): string {
  return (categoria ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

export function categoryBadgeStyle(categoria: string | null | undefined): CSSProperties {
  const key = normalizeCategoria(categoria);
  const style = CATEGORY_STYLES[key];
  if (!style) {
    return {
      backgroundColor: 'var(--pill-default-bg)',
      color: 'var(--pill-default-fg)',
    };
  }
  return {
    backgroundColor: `var(${style.bgVar})`,
    color: `var(${style.fgVar})`,
  };
}

export const KNOWN_CATEGORIES = [
  'Pós-graduação',
  'Graduação',
  'Intercâmbio',
  'Evento',
  'Bolsa',
  'Pesquisa',
  'Estágio',
  'Extensão',
  'Vestibular',
];

export const KNOWN_CAMPI = [
  'Darcy Ribeiro',
  'FGA (Gama)',
  'FCE (Ceilândia)',
  'FUP (Planaltina)',
  'Fazenda Água Limpa',
  'Geral',
];

export function buildAvailableYears(
  extraYears: number[] = [],
  baseYear: number = new Date().getFullYear(),
): number[] {
  const years = new Set<number>();
  const minYear = Math.min(2020, baseYear - 5);
  for (let year = baseYear + 1; year >= minYear; year -= 1) {
    years.add(year);
  }
  for (const year of extraYears) {
    if (Number.isInteger(year) && year >= 2000 && year <= baseYear + 5) {
      years.add(year);
    }
  }
  return Array.from(years).sort((a, b) => b - a);
}

export const KNOWN_YEARS = buildAvailableYears();

/**
 * Dias restantes até o prazo final (pode ser negativo se já venceu).
 * Retorna null quando a data não existe ou é inválida, para o chamador
 * decidir o que exibir em vez de quebrar.
 */
export function daysUntil(isoDate: string | null | undefined): number | null {
  if (!isoDate) return null;
  const deadline = new Date(isoDate);
  if (Number.isNaN(deadline.getTime())) return null;
  const today = new Date();
  const diffMs = deadline.getTime() - today.setHours(0, 0, 0, 0);
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
}

// Ex.: "24/11/2026 às 16:36", sempre no horário de Brasília.
export function formatDateTime(isoDate: string | null | undefined): string {
  if (!isoDate) return '';
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('day')}/${get('month')}/${get('year')} às ${get('hour')}:${get('minute')}`;
}

export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return 'não informado';
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return 'não informado';
  return date.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}
