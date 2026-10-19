"""Ponto de entrada principal da API GenResearch-Servidor."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from app.config import (
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    DEFAULT_WORKERS_COUNT
)
from app.routers import base, cache, documents, experiments, query, system, tasks
from app.services.request_queue import task_queue_manager
from app.services.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia o ciclo de vida da aplicação (startup e shutdown)."""
    # Startup: Inicialização reproduzível da persistência SQLite
    init_db()
    # Inicia os workers consumidores na fila compartilhada (mínimo 2 workers)
    task_queue_manager.start_workers(DEFAULT_WORKERS_COUNT)
    yield
    # Shutdown: Encerramento limpo das threads consumidoras
    task_queue_manager.stop_workers(timeout=3.0)


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
app.include_router(tasks.router)
app.include_router(cache.router)
app.include_router(experiments.router)
