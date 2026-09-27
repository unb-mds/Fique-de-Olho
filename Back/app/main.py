from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.core import database as database_module
from app.core.config import settings
from app.modules.editais.router import router as editais_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Inicializa o schema do banco no startup da aplicação."""
    database_module.init_db()
    yield


# Inicialização da aplicação FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API do projeto Fique de Olho — Centralizador, filtro e notificador de editais da UnB.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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
    """Endpoint de verificação de integridade do serviço (Healthcheck)."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


# Inclusão dos roteadores modulares
app.include_router(editais_router, prefix=settings.API_V1_STR)
