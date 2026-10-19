"""Rotas de observação do ambiente operacional e métricas do sistema."""

from typing import Any, Dict
from fastapi import APIRouter

from app.services.metrics import get_system_metrics, record_request
from app.services.system_info import get_system_info

router = APIRouter(prefix="/system", tags=["Sistema"])


@router.get("/info", summary="Retorna informações observáveis do ambiente operacional")
def read_system_info() -> Dict[str, Any]:
    """
    Coleta dados reais do sistema operacional, processador, RAM, swap, GPU e runtime local.
    Campos não disponíveis no ambiente são explicitamente sinalizados sem dados fictícios.
    """
    record_request()
    return get_system_info()


@router.get("/metrics", summary="Retorna métricas de sistema (instantâneas vs acumuladas)")
def read_system_metrics() -> Dict[str, Any]:
    """
    Retorna métricas de processo e sistema divididas em:
    - Métricas Instantâneas (RSS, VSZ, CPU %, threads ativas)
    - Métricas Acumuladas (CPU time, uptime, page faults, contadores de I/O)
    - Limitações técnicas da observabilidade documentadas
    """
    record_request()
    return get_system_metrics()
