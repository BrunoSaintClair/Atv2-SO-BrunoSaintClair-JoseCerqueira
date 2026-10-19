"""Rotas para consulta do catálogo e status dos experimentos."""

from typing import Any, Dict, List
from fastapi import APIRouter

from app.experiments.registry import get_experiments_catalog
from app.services.metrics import record_request

router = APIRouter(prefix="/experiments", tags=["Experimentos"])


@router.get("", summary="Lista os experimentos disponíveis e seus estados de implementação")
def list_experiments() -> List[Dict[str, Any]]:
    """
    Lista todos os experimentos previstos na atividade acadêmica (C1 a C6 e D),
    indicando variáveis investigadas e o estado atual de implementação de cada um.
    """
    record_request()
    return get_experiments_catalog()
