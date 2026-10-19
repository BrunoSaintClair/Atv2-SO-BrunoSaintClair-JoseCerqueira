"""Fila compartilhada de requisições com suporte a produtores e consumidores concorrentes."""

import queue
import threading
from typing import Any, Dict, Optional


class RequestQueueManager:
    """Gerencia a fila limitada de requisições e métricas de enfileiramento."""

    def __init__(self, maxsize: int = 50):
        self.maxsize = maxsize
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._enqueued_count = 0
        self._processed_count = 0
        self._lock = threading.Lock()

    def put(self, item: Any, block: bool = True, timeout: Optional[float] = None) -> None:
        """Enfileira uma requisição."""
        self._queue.put(item, block=block, timeout=timeout)
        with self._lock:
            self._enqueued_count += 1

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        """Desenfileira uma requisição."""
        item = self._queue.get(block=block, timeout=timeout)
        with self._lock:
            self._processed_count += 1
        return item

    def task_done(self) -> None:
        """Sinaliza conclusão da tarefa."""
        self._queue.task_done()

    def get_stats(self) -> Dict[str, Any]:
        """Retorna métricas da fila."""
        with self._lock:
            return {
                "current_size": self._queue.qsize(),
                "maxsize": self.maxsize,
                "total_enqueued": self._enqueued_count,
                "total_processed": self._processed_count
            }
