
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app.core.config import settings
from app.modules.editais.router import router as editais_router
from app.modules.usuarios.router import router as usuarios_router

from app.modules.notificacoes.processor import sendgrid_configurado
from app.modules.notificacoes.scheduler import executar_scheduler_notificacoes
from app.modules.scraper.scheduler import executar_scheduler_scraper

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if sendgrid_configurado():
        logger.info(
            "Envio de emails SendGrid configurado (remetente=%s).",
            settings.SENDGRID_FROM_EMAIL,
        )
    else:
        logger.warning(
            "Envio de emails SendGrid NÃO configurado: defina SENDGRID_API_KEY e "
            "SENDGRID_FROM_EMAIL nas variáveis de ambiente."
        )

    background_tasks = []
    if settings.NOTIFICATION_SCHEDULER_ENABLED:
        background_tasks.append(
            asyncio.create_task(
                executar_scheduler_notificacoes(
                    settings.NOTIFICATION_SCHEDULER_INTERVAL_SECONDS
                )
            )
        )
    if settings.SCRAPER_SCHEDULER_ENABLED:
        background_tasks.append(
            asyncio.create_task(
                executar_scheduler_scraper(
                    settings.SCRAPER_SCHEDULER_INTERVAL_HOURS * 3600,
                    run_on_startup=settings.SCRAPER_SCHEDULER_RUN_ON_STARTUP,
                )
            )
        )
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)


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
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/", include_in_schema=False)
def root():
    """Redireciona automaticamente a raiz para a documentação interativa Swagger."""
    return RedirectResponse(url="/docs")


@app.get("/ping", tags=["Health"])
def ping():
    """Endpoint leve de keep-alive que mantém o contêiner acordado sem consultar o banco."""
    return {"status": "awake"}



@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint de verificação de integridade do serviço (Healthcheck)."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,

        "database": db_status,
        "email_configured": sendgrid_configurado(),

    }


# Inclusão dos roteadores modulares:
# 1. Rota canônica com prefixo da API (/api/v1/editais)
app.include_router(editais_router, prefix=settings.API_V1_STR)

# 2. Rota de compatibilidade direta (/editais) para frontend e testes
app.include_router(editais_router, include_in_schema=False)
app.include_router(usuarios_router, prefix=settings.API_V1_STR)
