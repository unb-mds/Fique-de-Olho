"""Schemas Pydantic para serialização de editais na API."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class CampusSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


class TipoEditalSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


class CursoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


class EditalResponse(BaseModel):
    """Schema do edital compatível com o Frontend (React) e testes do Backend."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    status: str
    resumo: Optional[str] = None
    descricao: Optional[str] = None
    campus: Optional[str] = None
    unidade: Optional[str] = None
    categoria: Optional[str] = None
    data_publicacao: Optional[date] = None
    dataPublicacao: Optional[str] = None
    inicio_inscricao: Optional[date] = None
    fim_inscricao: Optional[date] = None
    prazoFinal: Optional[str] = None
    url_pdf: str
    urlDocumento: str
    status_processamento: str = "processado"
    vagas: Optional[int] = None
    valor: Optional[str] = None
    campi: List[CampusSchema] = []
    tipos: List[TipoEditalSchema] = []


class EditalDetailResponse(EditalResponse):
    """Schema com campos adicionais para a visualização detalhada do edital."""

    identificador_origem: Optional[str] = None
    texto_extraido: Optional[str] = None
    hash_conteudo: Optional[str] = None
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None


class SyncResult(BaseModel):
    """Resultado da execução do processo de sincronização/coleta de editais."""

    status: str
    coleta_id: int
    editais_encontrados: int
    novos_editais: int
    mensagem: str
