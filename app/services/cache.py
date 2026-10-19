"""Cache LRU compartilhado com métricas de acerto, erro e substituição."""

import threading
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple


class SharedLRUCache:
    """Cache compartilhado em memória com controle de concorrência e rastreamento de métricas."""

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str, use_lock: bool = True) -> Optional[Any]:
        """Obtém um item do cache atualizando sua posição de recência."""
        if use_lock:
            with self._lock:
                return self._get_unlocked(key)
        return self._get_unlocked(key)

    def _get_unlocked(self, key: str) -> Optional[Any]:
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, value: Any, use_lock: bool = True) -> None:
        """Armazena um item no cache, aplicando desalocação LRU se a capacidade for atingida."""
        if use_lock:
            with self._lock:
                self._put_unlocked(key, value)
        else:
            self._put_unlocked(key, value)

    def _put_unlocked(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
            self._evictions += 1

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas operacionais do cache."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total) if total > 0 else 0.0
            return {
                "capacity": self.capacity,
                "current_size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": round(hit_rate, 4)
            }

    def clear(self) -> None:
        """Limpa o cache e redefine contadores."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
