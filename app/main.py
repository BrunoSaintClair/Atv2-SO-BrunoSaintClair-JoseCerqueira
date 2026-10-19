"""Ponto de entrada principal da API GenResearch-Servidor."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from app.config import API_DESCRIPTION, API_TITLE, API_VERSION
from app.routers import base, documents, experiments, query, system
from app.services.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia o ciclo de vida da aplicação (startup e shutdown)."""
    # Startup: Inicialização reproduzível da persistência SQLite
    init_db()
    yield
    # Shutdown: Limpeza de recursos caso necessário


app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Inclusão dos roteadores modulares
app.include_router(base.router)
app.include_router(system.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(experiments.router)
