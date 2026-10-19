"""Rotas de administração e métricas do Cache Compartilhado LRU."""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.cache import rag_cache
from app.services.metrics import record_request

router = APIRouter(prefix="/cache", tags=["Cache Compartilhado"])


class CacheCapacityUpdateRequest(BaseModel):
    """Requisição para ajuste dinâmico de capacidade do cache."""
    capacity: int = Field(..., ge=1, le=10000, description="Nova capacidade máxima de itens no cache")


@router.get("/stats", summary="Retorna métricas operacionais do Cache LRU")
def get_cache_stats() -> Dict[str, Any]:
    """
    Retorna estatísticas detalhadas de concorrência e acertos do cache compartilhado:
    - hits, misses, evictions
    - taxa de acerto (hit rate)
    - tempo acumulado economizado (ms)
    - capacidade e ocupação atual
    """
    record_request()
    return rag_cache.get_stats()


@router.get("/keys", summary="Lista chaves do cache em ordem de recência (LRU -> MRU)")
def list_cache_keys() -> Dict[str, Any]:
    """
    Lista as chaves armazenadas no cache ordenadas da menos recentemente utilizada (LRU)
    à mais recentemente utilizada (MRU), comprovando o comportamento de substituição.
    """
    record_request()
    keys = rag_cache.inspect_keys()
    return {
        "current_size": len(keys),
        "capacity": rag_cache.capacity,
        "keys_lru_to_mru": keys
    }


@router.post("/capacity", summary="Altera dinamicamente a capacidade do cache (demonstração de eviction)")
def update_cache_capacity(payload: CacheCapacityUpdateRequest) -> Dict[str, Any]:
    """
    Redimensiona a capacidade do cache. Se a nova capacidade for menor do que a quantidade
    atual de itens, os itens menos recentemente utilizados são desalocados imediatamente.
    """
    record_request()
    try:
        evicted = rag_cache.set_capacity(payload.capacity)
        return {
            "new_capacity": payload.capacity,
            "items_evicted_now": evicted,
            "stats": rag_cache.get_stats()
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/clear", summary="Limpa todos os itens e métricas do cache")
def clear_cache() -> Dict[str, Any]:
    """Remove todas as entradas e redefine os contadores de hits, misses e evictions."""
    record_request()
    rag_cache.clear()
    return {
        "status": "cleared",
        "message": "Cache esvaziado e contadores operacionais reiniciados.",
        "stats": rag_cache.get_stats()
    }
