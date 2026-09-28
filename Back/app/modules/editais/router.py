from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.editais.service import list_editais_com_filtros

router = APIRouter(prefix="/editais", tags=["Editais"])


@router.get("/", response_model=List[Dict[str, Any]])
def list_editais(
    ano: Optional[int] = Query(None, description="Filtra editais pelo ano de publicação"),
    q: Optional[str] = Query(None, description="Busca textual por título"),
    busca: Optional[str] = Query(None, description="Alias para parâmetro de busca textual"),
    db: Session = Depends(get_db),
):
    """
    Retorna a listagem de editais com suporte a filtros dinâmicos:
    - `ano`: ano de publicação (ex: 2026)
    - `q` ou `busca`: termo de busca textual no título (case-insensitive)
    """
    termo_busca = q or busca

    try:
        editais_db = list_editais_com_filtros(db=db, ano=ano, q=termo_busca)
        if editais_db:
            return [
                {
                    "id": e.id,
                    "titulo": e.titulo,
                    "url_pagina": e.url_pagina,
                    "campus": e.campus,
                    "tipo": e.tipo,
                    "data_publicacao": e.data_publicacao.isoformat() if e.data_publicacao else None,
                    "status": e.status.value if hasattr(e.status, "value") else str(e.status),
                    "documentos": [
                        {
                            "id": doc.id,
                            "url_pdf": doc.url_pdf,
                            "tipo_documento": doc.tipo_documento.value if hasattr(doc.tipo_documento, "value") else str(doc.tipo_documento),
                        }
                        for doc in e.documentos
                    ],
                }
                for e in editais_db
            ]

        # Se filtros foram fornecidos e nada foi encontrado no banco, retorna lista vazia
        if ano is not None or termo_busca is not None:
            return []

    except Exception:
        # Se banco não responder ou estiver inacessível, mantém fallback
        pass

    # Mock inicial de setup para garantir compatibilidade quando o banco estiver vazio
    return [
        {
            "id": 1,
            "titulo": "Edital Monitoria DEG 01/2026",
            "campus": "Darcy Ribeiro",
            "status": "aberto",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB."
        }
    ]
