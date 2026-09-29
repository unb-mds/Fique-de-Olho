from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/editais", tags=["Editais"])



class EditalResponse(BaseModel):
    id: str
    titulo: str
    unidade: str
    categoria: str
    dataPublicacao: str
    prazoFinal: str
    status: str
    descricao: str
    urlDocumento: str


EDITAIS = [
    EditalResponse(
        id="1",
        titulo="Edital de Estágio DEG 01/2026",
        unidade="DEG",
        categoria="Estágio",
        dataPublicacao="2026-01-15",
        prazoFinal="2026-12-20",
        status="aberto",
        descricao=(
            "Seleção de estudantes de graduação para vagas de estágio nos departamentos da UnB."
        ),
        urlDocumento="https://deg.unb.br/",
    ),
    EditalResponse(
        id="2",
        titulo="Edital de Extensão DEX 02/2026",
        unidade="DEX",
        categoria="Extensão",
        dataPublicacao="2026-02-01",
        prazoFinal="2026-11-30",
        status="aberto",
        descricao=(
            "Chamada pública para projetos e bolsas de extensão universitária com inscrições abertas."
        ),
        urlDocumento="https://deg.unb.br/",
    ),
]


@router.get("/", response_model=List[EditalResponse])
def list_editais() -> List[EditalResponse]:
    """Retorna os editais disponíveis para consulta."""
    return EDITAIS


@router.get("/{edital_id}", response_model=EditalResponse)
def get_edital(edital_id: str) -> EditalResponse:
    """Retorna um edital pelo identificador público."""
    edital = next((item for item in EDITAIS if item.id == edital_id), None)
    if edital is None:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    return edital
