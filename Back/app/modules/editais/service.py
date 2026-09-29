from typing import List, Optional
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.core.database import Edital


def list_editais_com_filtros(
    db: Session,
    ano: Optional[int] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Edital]:
    """Constrói dinamicamente a consulta SQLAlchemy aplicando filtros por ano e busca textual."""
    query = db.query(Edital)

    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        query = query.filter(Edital.titulo.ilike(search_pattern))

    if ano is not None:
        query = query.filter(extract("year", Edital.data_publicacao) == ano)

    return query.order_by(Edital.data_publicacao.desc()).offset(skip).limit(limit).all()
