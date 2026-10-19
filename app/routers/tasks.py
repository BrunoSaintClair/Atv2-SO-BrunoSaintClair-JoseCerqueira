"""Rotas para gerenciamento de tarefas na Fila Compartilhada e controle de concorrência."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import DEFAULT_TOP_K, MAX_CONTEXT_CHARS, MAX_TOP_K, QUEUE_PUT_TIMEOUT
from app.services.metrics import record_request
from app.services.request_queue import QueueFullError, task_queue_manager

router = APIRouter(prefix="/tasks", tags=["Fila & Concorrência"])


class QueryTaskCreateRequest(BaseModel):
    """Esquema de requisição para enfileiramento de consulta RAG concorrente."""
    question: str = Field(..., min_length=2, description="Pergunta a ser processada de forma assíncrona")
    top_k: Optional[int] = Field(
        DEFAULT_TOP_K,
        ge=1,
        le=MAX_TOP_K,
        description="Quantidade de trechos relevantes a recuperar"
    )
    max_context_chars: Optional[int] = Field(
        MAX_CONTEXT_CHARS,
        ge=200,
        le=10000,
        description="Tamanho máximo do contexto delimitado"
    )
    use_cache: Optional[bool] = Field(
        True,
        description="Habilitar consulta e atualização do Cache LRU compartilhado"
    )


class WorkersScaleRequest(BaseModel):
    """Esquema para ajuste da quantidade de threads consumidoras (workers)."""
    num_workers: int = Field(..., ge=1, le=16, description="Novo número de workers consumidores ativos")


@router.post("/query", status_code=status.HTTP_202_ACCEPTED, summary="Enfileira uma consulta RAG na fila compartilhada")
def enqueue_query_task(payload: QueryTaskCreateRequest) -> Dict[str, Any]:
    """
    Submete uma consulta para a fila compartilhada limitada (operação de produtor).
    
    A requisição retorna imediatamente (não-bloqueante para a thread HTTP), informando
    o identificador único `task_id` e a posição na fila. O processamento ocorrerá de forma
    desacoplada pelas threads consumidoras (workers).
    
    Se a fila atingir sua capacidade máxima e o timeout expirar, retorna HTTP 503 (Fila Cheia).
    """
    record_request()
    try:
        record = task_queue_manager.submit_task(
            task_type="rag_query",
            payload=payload.model_dump(),
            timeout=QUEUE_PUT_TIMEOUT
        )
        return {
            "task_id": record.task_id,
            "status": record.status.value,
            "enqueued_at_unix": record.enqueued_at,
            "message": "Tarefa enfileirada com sucesso. Consulte o resultado em GET /tasks/{task_id}."
        }
    except QueueFullError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err)
        )


@router.get("/metrics", summary="Retorna métricas da fila compartilhada e dos workers concorrentes")
def get_queue_metrics() -> Dict[str, Any]:
    """
    Retorna métricas de concorrência e gerenciamento de tarefas:
    - Tarefas submetidas, concluídas, falhas, em processamento e pendentes
    - Capacidade da fila e ocupação atual
    - Número de workers consumidores ativos
    - Tempo médio de espera na fila e tempo médio de execução
    - Tarefas perdidas ou duplicadas
    """
    record_request()
    return task_queue_manager.get_metrics()


@router.get("/{task_id}", summary="Consulta o estado, resultado ou erro de uma tarefa")
def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Retorna o ciclo de vida de uma tarefa:
    - Status (queued, processing, completed, failed)
    - Thread consumidora responsável (worker_name)
    - Tempos de espera na fila (wait_time_ms) e de execução (execution_time_ms)
    - Resultado gerado ou mensagem de erro
    """
    record_request()
    task = task_queue_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa com task_id '{task_id}' não encontrada."
        )
    return task


@router.get("", summary="Lista tarefas recentes submetidas ao sistema")
def list_recent_tasks(limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    """Lista as tarefas mais recentes registradas na memória operacional da aplicação."""
    record_request()
    return task_queue_manager.list_tasks(limit=limit)


class QueueCapacityUpdateRequest(BaseModel):
    """Esquema para redimensionamento dinâmico da capacidade máxima da fila."""
    capacity: int = Field(..., ge=1, le=1000, description="Nova capacidade máxima de itens na fila")


@router.post("/workers/scale", summary="Ajusta o número de workers consumidores ativos")
def scale_workers_pool(payload: WorkersScaleRequest) -> Dict[str, Any]:
    """
    Redimensiona dinamicamente a quantidade de threads consumidoras da fila.
    Útil para comparar o desempenho concorrente com 1, 2 e 4 workers.
    """
    record_request()
    try:
        active = task_queue_manager.scale_workers(payload.num_workers)
        return {
            "message": f"Pool de consumidores ajustado para {active} worker(s).",
            "active_workers": active,
            "queue_metrics": task_queue_manager.get_metrics()
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/capacity", summary="Altera dinamicamente a capacidade máxima da fila compartilhada")
def update_queue_capacity(payload: QueueCapacityUpdateRequest) -> Dict[str, Any]:
    """
    Altera o limite máximo de armazenamento da fila de tarefas.
    Permite demonstrar de forma controlada o comportamento de saturação de fila cheia.
    """
    record_request()
    try:
        task_queue_manager.set_queue_capacity(payload.capacity)
        return {
            "message": f"Capacidade da fila alterada para {payload.capacity}.",
            "queue_metrics": task_queue_manager.get_metrics()
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
