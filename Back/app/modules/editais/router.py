from typing import List, Dict, Any
from fastapi import APIRouter

router = APIRouter(prefix="/editais", tags=["Editais"])


@router.get("/", response_model=List[Dict[str, Any]])
def list_editais():
    """Retorna listagem inicial de editais disponíveis (estrutura inicial de setup)."""
    return [
        {
            "id": 1,
            "titulo": "Edital Monitoria DEG 01/2026",
            "campus": "Darcy Ribeiro",
            "status": "aberto",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB."
        }
    ]
