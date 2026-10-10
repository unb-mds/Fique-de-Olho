from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.modules.editais.router import router as editais_router

# Inicialização da aplicação FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API do projeto Fique de Olho — Centralizador, filtro e notificador de editais da UnB.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuração de CORS (Permitir comunicação com frontends locais como React/Vite/Next)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restringir aos domínios autorizados
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root():
    """Redireciona automaticamente a raiz para a documentação interativa Swagger."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint de verificação de integridade do serviço (Healthcheck) e banco de dados."""
    db_status = "connected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"disconnected: {e}"

    is_healthy = db_status == "connected"
    content = {
        "status": "healthy" if is_healthy else "unhealthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": db_status,
    }
    return JSONResponse(
        content=content,
        status_code=status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# Inclusão dos roteadores modulares
app.include_router(editais_router, prefix=settings.API_V1_STR)
app.include_router(editais_router, include_in_schema=False)
