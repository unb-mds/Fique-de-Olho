
export interface EditalDocumento {
  id: number;
  url_pdf: string;
  tipo_documento: string;
  titulo?: string;
}

export interface Edital {
  id: string;
  titulo: string;
  unidade: string;
  categoria: string;
  dataPublicacao: string;
  prazoFinal: string;
  status: 'aberto' | 'fechado';
  descricao: string;
  urlDocumento: string;

  // Metadados adicionais
  orgaoEmissor?: string;
  assunto?: string;
  inicioInscricao?: string;
  documentos?: EditalDocumento[];

  // Campos opcionais existentes
  vagas?: number;
  valor?: string;
}

