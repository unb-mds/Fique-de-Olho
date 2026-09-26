import type { CSSProperties } from 'react';

// Mapeia cada categoria de edital para as cores de badge usadas no protótipo.
// Adicione novas categorias aqui conforme o backend passar a retorná-las.
const CATEGORY_STYLES: Record<string, { bgVar: string; fgVar: string }> = {
  pibic: { bgVar: '--pill-pibic-bg', fgVar: '--pill-pibic-fg' },
  vestibular: { bgVar: '--pill-vestibular-bg', fgVar: '--pill-vestibular-fg' },
  estagio: { bgVar: '--pill-estagio-bg', fgVar: '--pill-estagio-fg' },
  monitoria: { bgVar: '--pill-monitoria-bg', fgVar: '--pill-monitoria-fg' },
  extensao: { bgVar: '--pill-extensao-bg', fgVar: '--pill-extensao-fg' },
  pesquisa: { bgVar: '--pill-pesquisa-bg', fgVar: '--pill-pesquisa-fg' },
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
  'Pesquisa',
  'Estágio',
  'PIBIC',
  'Extensão',
  'Monitoria',
  'Vestibular',
];

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
