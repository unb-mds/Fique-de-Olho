export interface Edital {
  id: string;
  titulo: string;
  unidade: string;
  categoria: string;
  dataPublicacao: string; // ISO date
  prazoFinal: string; // ISO date
  status: 'aberto' | 'fechado';
  descricao: string;
  urlDocumento: string;
  // Campos opcionais: nem toda resposta da API precisa trazê-los,
  // os componentes tratam a ausência deles graciosamente.
  vagas?: number;
  valor?: string;
}
