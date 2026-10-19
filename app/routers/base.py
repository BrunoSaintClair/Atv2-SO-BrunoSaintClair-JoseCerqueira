"""Rotas base da aplicação: identificação e health check."""

import time
from typing import Any, Dict
from fastapi import APIRouter

from app.config import API_DESCRIPTION, API_TITLE, API_VERSION
from app.services.metrics import record_request

router = APIRouter(tags=["Base"])
_start_time = time.time()


@router.get("/", summary="Identificação breve do serviço")
def get_root() -> Dict[str, Any]:
    """Retorna a identificação básica da aplicação e referências para documentação."""
    record_request()
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "description": API_DESCRIPTION,
        "docs_url": "/docs",
        "endpoints": {
            "health": "/health",
            "system_info": "/system/info",
            "system_metrics": "/system/metrics",
            "experiments": "/experiments"
        }
    }


@router.get("/health", summary="Verifica se a aplicação está operacional")
def get_health() -> Dict[str, Any]:
    """Retorna o estado operacional e o tempo de atividade da API."""
    record_request()
    uptime_seconds = round(time.time() - _start_time, 2)
    return {
        "status": "healthy",
        "uptime_seconds": uptime_seconds,
        "timestamp_unix": time.time()
    }
