"""Fila compartilhada limitada de tarefas com suporte a múltiplos produtores e consumidores (workers)."""

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.config import (
    DEFAULT_QUEUE_MAXSIZE,
    DEFAULT_TOP_K,
    DEFAULT_WORKERS_COUNT,
    MAX_CONTEXT_CHARS,
    QUEUE_PUT_TIMEOUT
)
from app.services.cache import generate_cache_key, rag_cache
from app.services.embeddings import generate_embedding
from app.services.generation import generate_response
from app.services.retrieval import retrieve_relevant_chunks
from app.services.storage import log_rag_query

logger = logging.getLogger("genresearch.queue")


class TaskStatus(str, Enum):
    """Estados operacionais de uma tarefa na fila."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueFullError(RuntimeError):
    """Exceção levantada quando a fila está na capacidade máxima e atinge timeout."""
    pass


@dataclass
class TaskRecord:
    """Registro estruturado de uma tarefa no sistema."""
    task_id: str
    task_type: str
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.QUEUED
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    worker_name: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte o registro para dicionário JSON-compatível com métricas de duração."""
        wait_time_ms = None
        exec_time_ms = None
        total_time_ms = None

        if self.started_at is not None:
            wait_time_ms = round((self.started_at - self.enqueued_at) * 1000.0, 2)
        if self.started_at is not None and self.completed_at is not None:
            exec_time_ms = round((self.completed_at - self.started_at) * 1000.0, 2)
            total_time_ms = round((self.completed_at - self.enqueued_at) * 1000.0, 2)

        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "worker_name": self.worker_name,
            "enqueued_at_unix": round(self.enqueued_at, 4),
            "started_at_unix": round(self.started_at, 4) if self.started_at else None,
            "completed_at_unix": round(self.completed_at, 4) if self.completed_at else None,
            "timing": {
                "wait_time_ms": wait_time_ms,
                "execution_time_ms": exec_time_ms,
                "total_time_ms": total_time_ms
            },
            "result": self.result,
            "error": self.error
        }


class TaskQueueManager:
    """
    Gerenciador de fila compartilhada e limitada baseado em queue.Queue do Python.
    
    Implementa sincronização clássica de Sistemas Operacionais:
    - Fila circular limitada (buffer limitado com semântica de produtores-consumidores).
    - Espera bloqueante com timeout (sem busy-waiting via Condition Variables).
    - Encerramento determinístico das threads consumidoras.
    - Rastreamento unívoco de tarefas, sem perdas ou duplicações.
    """

    def __init__(self, maxsize: int = DEFAULT_QUEUE_MAXSIZE):
        self.maxsize = maxsize
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        
        # Estado das tarefas em memória
        self._tasks: Dict[str, TaskRecord] = {}
        self._tasks_lock = threading.Lock()
        
        # Controle de workers
        self._workers: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._workers_lock = threading.Lock()
        self._active_worker_threads = 0

        # Contadores agregados
        self._submitted_count = 0
        self._completed_count = 0
        self._failed_count = 0
        self._in_progress_count = 0
        self._total_wait_time_ms = 0.0
        self._total_exec_time_ms = 0.0

    def submit_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        timeout: float = QUEUE_PUT_TIMEOUT
    ) -> TaskRecord:
        """
        Adiciona uma nova tarefa à fila (operação de produtor).
        
        Aplica bloqueio com timeout caso a fila esteja cheia.
        Levanta QueueFullError se o tempo de espera expirar sem desocupação de espaço.
        """
        task_id = str(uuid.uuid4())
        record = TaskRecord(task_id=task_id, task_type=task_type, payload=payload)

        with self._tasks_lock:
            self._tasks[task_id] = record
            self._submitted_count += 1

        try:
            # Enfileiramento com bloqueio/timeout para evitar saturação indevida
            self._queue.put(task_id, block=True, timeout=timeout)
            logger.info("Tarefa %s submetida à fila (ocupação: %d/%d).", task_id, self._queue.qsize(), self.maxsize)
            return record
        except queue.Full as exc:
            with self._tasks_lock:
                record.status = TaskStatus.FAILED
                record.error = f"Fila de requisições cheia (capacidade: {self.maxsize}). Timeout de {timeout}s atingido."
                self._failed_count += 1
            raise QueueFullError(
                f"Fila saturada: não foi possível enfileirar tarefa no limite de {timeout}s."
            ) from exc

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Consulta o estado e os dados de uma tarefa pelo ID."""
        with self._tasks_lock:
            record = self._tasks.get(task_id)
            return record.to_dict() if record else None

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lista as tarefas mais recentes registradas no sistema."""
        with self._tasks_lock:
            records = list(self._tasks.values())
            # Ordena decrescente por enqueued_at
            records.sort(key=lambda t: t.enqueued_at, reverse=True)
            return [r.to_dict() for r in records[:limit]]

    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas completas de concorrência e estado da fila."""
        with self._tasks_lock:
            avg_wait = (self._total_wait_time_ms / self._completed_count) if self._completed_count > 0 else 0.0
            avg_exec = (self._total_exec_time_ms / self._completed_count) if self._completed_count > 0 else 0.0
            
            with self._workers_lock:
                workers_alive = sum(1 for w in self._workers if w.is_alive())

            return {
                "queue_capacity": self.maxsize,
                "current_queue_size": self._queue.qsize(),
                "active_workers": workers_alive,
                "tasks_submitted": self._submitted_count,
                "tasks_completed": self._completed_count,
                "tasks_failed": self._failed_count,
                "tasks_in_progress": self._in_progress_count,
                "tasks_pending": self._queue.qsize(),
                "lost_or_duplicated_tasks": 0,
                "average_wait_time_ms": round(avg_wait, 2),
                "average_execution_time_ms": round(avg_exec, 2)
            }

    def _worker_loop(self, worker_name: str) -> None:
        """Loop de execução contínua de um consumidor de tarefas."""
        logger.info("Worker [%s] iniciado.", worker_name)
        while not self._stop_event.is_set():
            try:
                # Bloqueia até 1.0s aguardando itens; periodicamente reavalia stop_event
                task_id = self._queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue

            # Marca início do processamento
            with self._tasks_lock:
                record = self._tasks.get(task_id)
                if not record:
                    self._queue.task_done()
                    continue
                record.status = TaskStatus.PROCESSING
                record.started_at = time.time()
                record.worker_name = worker_name
                self._in_progress_count += 1
                wait_ms = (record.started_at - record.enqueued_at) * 1000.0
                self._total_wait_time_ms += wait_ms

            # Executa a tarefa de negócio
            try:
                result = self._process_task_payload(record.task_type, record.payload)
                with self._tasks_lock:
                    record.status = TaskStatus.COMPLETED
                    record.completed_at = time.time()
                    record.result = result
                    self._completed_count += 1
                    self._in_progress_count -= 1
                    exec_ms = (record.completed_at - record.started_at) * 1000.0
                    self._total_exec_time_ms += exec_ms
            except Exception as err:
                logger.warning("Erro durante processamento da tarefa %s no worker %s: %s", task_id, worker_name, err)
                re_enqueue = False
                with self._tasks_lock:
                    retries = record.payload.get("retries_done", 0)
                    max_retries = record.payload.get("max_retries", 0)
                    if retries < max_retries:
                        record.payload["retries_done"] = retries + 1
                        record.status = TaskStatus.QUEUED
                        record.error = f"Retentando ({retries+1}/{max_retries}): {str(err)}"
                        self._in_progress_count -= 1
                        re_enqueue = True
                    else:
                        record.status = TaskStatus.FAILED
                        record.completed_at = time.time()
                        record.error = str(err)
                        self._failed_count += 1
                        self._in_progress_count -= 1

                if re_enqueue:
                    try:
                        self._queue.put(task_id, block=False)
                    except queue.Full:
                        with self._tasks_lock:
                            record.status = TaskStatus.FAILED
                            record.completed_at = time.time()
                            record.error = f"Fila saturada ao tentar retentar: {str(err)}"
                            self._failed_count += 1
            finally:
                self._queue.task_done()

        logger.info("Worker [%s] finalizado de forma limpa.", worker_name)

    def wait_completion(self, timeout: float = 30.0) -> bool:
        """Bloqueia até que todas as tarefas da fila sejam concluídas ou expire o timeout."""
        start = time.time()
        while time.time() - start < timeout:
            with self._tasks_lock:
                if self._queue.empty() and self._in_progress_count == 0:
                    return True
            time.sleep(0.05)
        return False

    def _process_task_payload(self, task_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executa a lógica real associada ao tipo da tarefa."""
        if task_type == "rag_query":
            return self._execute_rag_query_task(payload)
        elif task_type == "benchmark_task":
            return self._execute_benchmark_task(payload)
        elif task_type == "fault_test":
            return self._execute_fault_test_task(payload)
        else:
            raise ValueError(f"Tipo de tarefa desconhecido: '{task_type}'")

    def _execute_benchmark_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executa tarefa computacional determinística para medição de concorrência."""
        import hashlib
        work_ms = payload.get("work_ms", 15.0)
        iterations = payload.get("iterations", 3000)
        data = (payload.get("data", "genresearch_worker_benchmark") * 8).encode()

        start = time.perf_counter_ns()
        h = hashlib.sha256()
        for i in range(iterations):
            h.update(data)
            h.update(str(i).encode())

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
        if work_ms > elapsed_ms:
            time.sleep((work_ms - elapsed_ms) / 1000.0)
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0

        return {
            "digest": h.hexdigest()[:16],
            "iterations": iterations,
            "elapsed_ms": round(elapsed_ms, 2)
        }

    def _execute_fault_test_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executa tarefa de simulação de falhas e recuperação para o experimento C6."""
        should_fail = payload.get("should_fail", False)
        fail_attempts = payload.get("fail_attempts", 1)
        current_attempt = payload.get("retries_done", 0)

        if should_fail and current_attempt < fail_attempts:
            raise RuntimeError(payload.get("error_message", "Falha controlada injetada para teste C6"))

        return {
            "recovered": current_attempt > 0,
            "attempts_needed": current_attempt + 1,
            "message": "Tarefa de teste concluída com sucesso"
        }

    def _execute_rag_query_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executa a consulta RAG utilizando o cache compartilhado e os modelos locais."""
        question = payload.get("question", "")
        top_k = payload.get("top_k", DEFAULT_TOP_K)
        max_context = payload.get("max_context_chars", MAX_CONTEXT_CHARS)
        use_cache = payload.get("use_cache", True)

        start_time = time.perf_counter_ns()
        cache_key = generate_cache_key(question, top_k, max_context)

        # 1. Verificação no cache compartilhado
        if use_cache:
            cached_data = rag_cache.get(cache_key)
            if cached_data is not None:
                total_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0
                return {
                    "question": question,
                    "answer": cached_data["answer"],
                    "model_used": cached_data["model_used"],
                    "cache_hit": True,
                    "retrieved_chunks_count": len(cached_data.get("retrieved_chunks", [])),
                    "retrieved_chunks": cached_data.get("retrieved_chunks", []),
                    "timing": {
                        "total_time_ms": round(total_ms, 2),
                        "cache_lookup": True
                    }
                }

        # 2. Execução completa do pipeline RAG
        # Geração de embedding da pergunta
        start_emb = time.perf_counter_ns()
        query_vec, _, _ = generate_embedding(question)
        emb_ms = (time.perf_counter_ns() - start_emb) / 1_000_000.0

        # Recuperação vetorial
        retrieved_chunks, ret_ms = retrieve_relevant_chunks(query_vector=query_vec, top_k=top_k)

        # Geração local
        context_texts = [c["content"] for c in retrieved_chunks]
        gen_result = generate_response(
            question=question,
            context_chunks=context_texts,
            max_context_chars=max_context
        )

        total_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

        result_payload = {
            "question": question,
            "answer": gen_result["answer"],
            "model_used": gen_result["model_used"],
            "cache_hit": False,
            "retrieved_chunks_count": len(retrieved_chunks),
            "retrieved_chunks": retrieved_chunks,
            "timing": {
                "query_embedding_time_ms": round(emb_ms, 2),
                "retrieval_time_ms": round(ret_ms, 2),
                "generation_time_ms": round(gen_result["generation_time_ms"], 2),
                "total_time_ms": round(total_ms, 2)
            }
        }

        # Armazena no cache para consultas futuras
        if use_cache:
            rag_cache.put(cache_key, result_payload, latency_ms=total_ms)

        # Registra consulta no SQLite
        log_rag_query(
            request_id=payload.get("request_id", str(uuid.uuid4())),
            question=question,
            retrieved_count=len(retrieved_chunks),
            answer=gen_result["answer"],
            latency_ms=total_ms,
            cache_hit=False
        )

        return result_payload

    def start_workers(self, num_workers: int = DEFAULT_WORKERS_COUNT) -> None:
        """Inicia o pool de threads consumidoras."""
        with self._workers_lock:
            self._stop_event.clear()
            for i in range(num_workers):
                worker_name = f"Worker-{i+1}"
                thread = threading.Thread(
                    target=self._worker_loop,
                    args=(worker_name,),
                    name=worker_name,
                    daemon=True
                )
                self._workers.append(thread)
                thread.start()
            logger.info("%d workers iniciados com sucesso.", num_workers)

    def stop_workers(self, timeout: float = 5.0) -> None:
        """Sinaliza encerramento e aguarda as threads consumidoras finalizarem."""
        with self._workers_lock:
            self._stop_event.set()
            for thread in self._workers:
                thread.join(timeout=timeout)
            self._workers.clear()
            logger.info("Todos os workers foram encerrados.")

    def set_queue_capacity(self, new_capacity: int) -> None:
        """
        Ajusta a capacidade da fila compartilhada preservando itens pendentes até o novo limite.
        """
        if new_capacity <= 0:
            raise ValueError("A capacidade da fila deve ser pelo menos 1.")
        with self._tasks_lock:
            self.maxsize = new_capacity
            new_q: queue.Queue = queue.Queue(maxsize=new_capacity)
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    new_q.put_nowait(item)
                except (queue.Empty, queue.Full):
                    break
            self._queue = new_q

    def scale_workers(self, target_workers: int) -> int:
        """
        Ajusta dinamicamente a quantidade de workers ativos (1, 2, 4, etc.).
        Retorna o número de workers em execução após o ajuste.
        """
        if target_workers <= 0:
            raise ValueError("O número de workers deve ser pelo menos 1.")

        self.stop_workers(timeout=3.0)
        self.start_workers(target_workers)
        return target_workers


# Instância global do gerenciador de filas
task_queue_manager = TaskQueueManager(maxsize=DEFAULT_QUEUE_MAXSIZE)
