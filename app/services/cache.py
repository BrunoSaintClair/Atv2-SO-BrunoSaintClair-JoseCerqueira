"""Cache LRU compartilhado thread-safe com métricas de acerto, erro e substituição."""

import hashlib
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from app.config import DEFAULT_CACHE_CAPACITY


def generate_cache_key(question: str, top_k: int, max_context_chars: int) -> str:
    """
    Gera uma chave determinística para o cache baseada nos parâmetros da consulta RAG.
    
    A normalização do texto (remoção de espaços e minúsculas) garante consistência,
    enquanto os parâmetros estruturais (top_k, max_context_chars) garantem que
    consultas com escopos diferentes não compartilhem respostas inadequadas.
    """
    normalized_q = " ".join(question.strip().lower().split())
    raw_key = f"{normalized_q}|top_k={top_k}|max_ctx={max_context_chars}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    return f"rag_{digest}_{top_k}_{max_context_chars}"


class SharedLRUCache:
    """
    Cache LRU (Least Recently Used) compartilhado em memória para consultas RAG.
    
    Características de Sistemas Operacionais:
    - Proteção de região crítica contra condições de corrida via threading.Lock.
    - Política determinística de substituição LRU baseada em ordem de acesso (OrderedDict).
    - Métricas completas: hits, misses, evictions, taxa de acerto e tempo acumulado de CPU/GPU economizado.
    """

    def __init__(self, capacity: int = DEFAULT_CACHE_CAPACITY):
        if capacity <= 0:
            raise ValueError("A capacidade do cache deve ser maior que zero.")
        self.capacity = capacity
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_time_saved_ms = 0.0

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Consulta um item no cache. Se presente, atualiza a posição para o topo de recência (MRU).
        Registra hit ou miss de forma atômica.
        """
        with self._lock:
            if key in self._cache:
                self._hits += 1
                self._cache.move_to_end(key, last=True)
                item = self._cache[key]
                # Contabiliza a economia de tempo com base no tempo de geração original
                saved_ms = item.get("saved_latency_ms", 0.0)
                self._total_time_saved_ms += saved_ms
                return item["data"]
            
            self._misses += 1
            return None

    def put(self, key: str, value: Any, latency_ms: float = 0.0) -> None:
        """
        Armazena ou atualiza um item no cache.
        
        Se a capacidade for excedida, despeja (evict) a entrada menos recentemente usada (LRU).
        """
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key, last=True)
            self._cache[key] = {
                "data": value,
                "saved_latency_ms": latency_ms
            }
            if len(self._cache) > self.capacity:
                # Remove o primeiro elemento (o menos recentemente utilizado)
                self._cache.popitem(last=False)
                self._evictions += 1

    def set_capacity(self, new_capacity: int) -> int:
        """
        Redimensiona dinamicamente a capacidade do cache.
        Despeja itens excedentes imediatamente se a nova capacidade for menor.
        Retorna o número de itens despejados na operação.
        """
        if new_capacity <= 0:
            raise ValueError("A capacidade do cache deve ser positiva.")
        
        evicted_now = 0
        with self._lock:
            self.capacity = new_capacity
            while len(self._cache) > self.capacity:
                self._cache.popitem(last=False)
                self._evictions += 1
                evicted_now += 1
        return evicted_now

    def inspect_keys(self) -> List[str]:
        """
        Retorna as chaves em ordem de recência (do mais antigo ao mais recentemente acessado).
        Útil para demonstrações acadêmicas e testes do algoritmo LRU.
        """
        with self._lock:
            return list(self._cache.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas operacionais do cache."""
        with self._lock:
            total_lookups = self._hits + self._misses
            hit_rate = (self._hits / total_lookups) if total_lookups > 0 else 0.0
            return {
                "capacity": self.capacity,
                "current_size": len(self._cache),
                "total_lookups": total_lookups,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": round(hit_rate, 4),
                "total_time_saved_ms": round(self._total_time_saved_ms, 2)
            }

    def clear(self) -> None:
        """Esvazia o cache e zera contadores operacionais."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._total_time_saved_ms = 0.0


# Instância global compartilhada do cache LRU
rag_cache = SharedLRUCache(capacity=DEFAULT_CACHE_CAPACITY)
