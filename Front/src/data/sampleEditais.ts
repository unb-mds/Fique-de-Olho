import type { Edital } from '@/services/types';

export const SAMPLE_EDITAIS: Edital[] = [
  {
    id: 'exemplo-sisu-2027',
    titulo: 'SISU 2027 — Ingresso nos cursos de graduação da UnB',
    unidade: 'Todos os campi',
    categoria: 'Vestibular',
    dataPublicacao: '2027-01-05',
    prazoFinal: '2027-01-20',
    status: 'aberto',
    descricao:
      'Seleção para os cursos de graduação da UnB via SISU, utilizando as notas do ENEM. Mais de 150 cursos em quatro campi, com reserva de vagas para cotas sociais, PPI e escola pública.',
    urlDocumento: 'https://www.unb.br/',
    vagas: 150,
  },
  {
    id: 'exemplo-pibic-2027',
    titulo: 'Programa de iniciação científica 2027',
    unidade: 'Decanato de Pesquisa e Inovação',
    categoria: 'Pesquisa',
    dataPublicacao: '2026-11-01',
    prazoFinal: '2027-01-28',
    status: 'aberto',
    descricao:
      'Seleção de estudantes para projetos de pesquisa com orientação docente, formação científica e bolsa mensal.',
    urlDocumento: 'https://www.unb.br/',
    vagas: 24,
    valor: 'R$ 700,00',
  },
  {
    id: 'exemplo-extensao-2027',
    titulo: 'Bolsas para projetos de extensão',
    unidade: 'Decanato de Extensão',
    categoria: 'Extensão',
    dataPublicacao: '2026-10-18',
    prazoFinal: '2027-02-15',
    status: 'aberto',
    descricao:
      'Apoio a estudantes que atuam em projetos de extensão ligados à comunidade do Distrito Federal.',
    urlDocumento: 'https://www.unb.br/',
    vagas: 12,
    valor: 'R$ 600,00',
  },
];

export function getSampleEdital(id: string | undefined) {
  return SAMPLE_EDITAIS.find((edital) => edital.id === id);
}
