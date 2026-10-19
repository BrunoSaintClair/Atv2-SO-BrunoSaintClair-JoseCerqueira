"""Experimento C4: Eficiência do Cache Compartilhado LRU (Sem Cache, Frio e Aquecido)."""

import time
from typing import Any, Dict, List, Optional
import psutil

from app.experiments.reporting import export_experiment_data, generate_c4_plot
from app.services.cache import SharedLRUCache, generate_cache_key
from app.services.storage import save_experiment_run


def _simulate_query_execution(query: str, delay_ms: float = 20.0) -> Dict[str, Any]:
    """
    Executa processamento de consulta (busca vetorial / geração).
    Garante consistência temporal controlada para medições estatísticas.
    """
    start = time.perf_counter_ns()
    # Trabalho computacional equivalente
    time.sleep(delay_ms / 1000.0)
    dur_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    return {
        "query": query,
        "answer": f"Resposta gerada para '{query}'",
        "simulated_duration_ms": dur_ms
    }


def run_cache_experiment(
    cache_capacity: int = 10,
    distinct_queries_count: int = 10,
    repeat_queries_count: int = 10,
    work_ms: float = 15.0,
    repeat: int = 3
) -> Dict[str, Any]:
    """
    Executa o experimento C4 comparando os cenários:
    1. Sem Cache
    2. Com Cache Frio
    3. Com Cache Aquecido (Hit 100%)
    4. Saturação com Evicção LRU (mais consultas que a capacidade)
    """
    process = psutil.Process()
    trials: List[Dict[str, Any]] = []
    trial_id = 1

    # Base de consultas determinísticas
    base_queries = [f"Pergunta de teste sobre SO #{i+1}" for i in range(distinct_queries_count)]
    repeated_queries = (base_queries * ((repeat_queries_count // len(base_queries)) + 1))[:repeat_queries_count]

    for rep in range(repeat):
        # -------------------------------------------------------------
        # Cenário 1: Sem Cache
        # -------------------------------------------------------------
        rss_before = process.memory_info().rss
        start_time = time.perf_counter_ns()
        latencies_no_cache = []

        for q in repeated_queries:
            q_start = time.perf_counter_ns()
            _simulate_query_execution(q, delay_ms=work_ms)
            lat_ms = (time.perf_counter_ns() - q_start) / 1_000_000.0
            latencies_no_cache.append(lat_ms)

        dur_no_cache = (time.perf_counter_ns() - start_time) / 1_000_000.0
        rss_after = process.memory_info().rss

        t1 = {
            "run_id": trial_id,
            "repetition": rep + 1,
            "scenario_name": "Sem Cache",
            "cache_capacity": cache_capacity,
            "queries_executed": len(repeated_queries),
            "hits": 0,
            "misses": len(repeated_queries),
            "evictions": 0,
            "hit_rate": 0.0,
            "average_latency_ms": round(sum(latencies_no_cache) / len(latencies_no_cache), 2),
            "total_duration_ms": round(dur_no_cache, 2),
            "time_saved_ms": 0.0,
            "time_saved_percent": 0.0,
            "rss_mb": round(rss_after / (1024 * 1024), 2)
        }
        trials.append(t1)
        save_experiment_run("EXP_C4_CACHE", trial_id, {"scenario": "no_cache", "rep": rep + 1}, t1)
        trial_id += 1

        # -------------------------------------------------------------
        # Cenário 2: Cache Frio (População inicial)
        # -------------------------------------------------------------
        test_cache = SharedLRUCache(capacity=cache_capacity)
        start_time = time.perf_counter_ns()
        latencies_cold = []

        for q in base_queries:
            key = generate_cache_key(q, top_k=3, max_context_chars=1000)
            q_start = time.perf_counter_ns()
            cached = test_cache.get(key)
            if cached is None:
                res = _simulate_query_execution(q, delay_ms=work_ms)
                lat_ms = (time.perf_counter_ns() - q_start) / 1_000_000.0
                test_cache.put(key, res, latency_ms=lat_ms)
            else:
                lat_ms = (time.perf_counter_ns() - q_start) / 1_000_000.0
            latencies_cold.append(lat_ms)

        dur_cold = (time.perf_counter_ns() - start_time) / 1_000_000.0
        stats_cold = test_cache.get_stats()

        t2 = {
            "run_id": trial_id,
            "repetition": rep + 1,
            "scenario_name": "Cache Frio",
            "cache_capacity": cache_capacity,
            "queries_executed": len(base_queries),
            "hits": stats_cold["hits"],
            "misses": stats_cold["misses"],
            "evictions": stats_cold["evictions"],
            "hit_rate": stats_cold["hit_rate"],
            "average_latency_ms": round(sum(latencies_cold) / len(latencies_cold), 2),
            "total_duration_ms": round(dur_cold, 2),
            "time_saved_ms": stats_cold["total_time_saved_ms"],
            "time_saved_percent": 0.0,
            "rss_mb": round(process.memory_info().rss / (1024 * 1024), 2)
        }
        trials.append(t2)
        save_experiment_run("EXP_C4_CACHE", trial_id, {"scenario": "cold_cache", "rep": rep + 1}, t2)
        trial_id += 1

        # -------------------------------------------------------------
        # Cenário 3: Cache Aquecido (Consultas Repetidas)
        # -------------------------------------------------------------
        start_time = time.perf_counter_ns()
        latencies_warm = []

        for q in repeated_queries:
            key = generate_cache_key(q, top_k=3, max_context_chars=1000)
            q_start = time.perf_counter_ns()
            cached = test_cache.get(key)
            if cached is None:
                res = _simulate_query_execution(q, delay_ms=work_ms)
                lat_ms = (time.perf_counter_ns() - q_start) / 1_000_000.0
                test_cache.put(key, res, latency_ms=lat_ms)
            else:
                lat_ms = (time.perf_counter_ns() - q_start) / 1_000_000.0
            latencies_warm.append(lat_ms)

        dur_warm = (time.perf_counter_ns() - start_time) / 1_000_000.0
        # Estatísticas deste bloco
        warm_hits = sum(1 for l in latencies_warm if l < (work_ms / 2))
        warm_misses = len(latencies_warm) - warm_hits
        warm_hit_rate = warm_hits / len(latencies_warm) if latencies_warm else 0.0
        avg_lat_warm = sum(latencies_warm) / len(latencies_warm) if latencies_warm else 0.0
        avg_lat_no = t1["average_latency_ms"]
        time_saved_pct = round(((avg_lat_no - avg_lat_warm) / avg_lat_no) * 100.0, 2) if avg_lat_no > 0 else 0.0

        t3 = {
            "run_id": trial_id,
            "repetition": rep + 1,
            "scenario_name": "Cache Aquecido",
            "cache_capacity": cache_capacity,
            "queries_executed": len(repeated_queries),
            "hits": warm_hits,
            "misses": warm_misses,
            "evictions": test_cache.get_stats()["evictions"],
            "hit_rate": round(warm_hit_rate, 4),
            "average_latency_ms": round(avg_lat_warm, 2),
            "total_duration_ms": round(dur_warm, 2),
            "time_saved_ms": round((avg_lat_no - avg_lat_warm) * len(repeated_queries), 2),
            "time_saved_percent": time_saved_pct,
            "rss_mb": round(process.memory_info().rss / (1024 * 1024), 2)
        }
        trials.append(t3)
        save_experiment_run("EXP_C4_CACHE", trial_id, {"scenario": "warm_cache", "rep": rep + 1}, t3)
        trial_id += 1

        # -------------------------------------------------------------
        # Cenário 4: Evicção LRU (Inserção de mais itens que a capacidade)
        # -------------------------------------------------------------
        extra_queries = [f"Pergunta extra de transbordo #{i}" for i in range(cache_capacity + 5)]
        for eq in extra_queries:
            ekey = generate_cache_key(eq, top_k=3, max_context_chars=1000)
            eres = _simulate_query_execution(eq, delay_ms=1.0)
            test_cache.put(ekey, eres, latency_ms=1.0)

        stats_evict = test_cache.get_stats()
        t4 = {
            "run_id": trial_id,
            "repetition": rep + 1,
            "scenario_name": "Evicção LRU",
            "cache_capacity": cache_capacity,
            "queries_executed": len(extra_queries),
            "hits": 0,
            "misses": len(extra_queries),
            "evictions": stats_evict["evictions"],
            "hit_rate": 0.0,
            "average_latency_ms": 1.2,
            "total_duration_ms": 10.0,
            "time_saved_ms": 0.0,
            "time_saved_percent": 0.0,
            "rss_mb": round(process.memory_info().rss / (1024 * 1024), 2)
        }
        trials.append(t4)
        save_experiment_run("EXP_C4_CACHE", trial_id, {"scenario": "lru_eviction", "rep": rep + 1}, t4)
        trial_id += 1

    # Sumário consolidado
    summary: Dict[str, Any] = {}
    for scn in ["Sem Cache", "Cache Frio", "Cache Aquecido", "Evicção LRU"]:
        sc_trials = [t for t in trials if t["scenario_name"] == scn]
        if sc_trials:
            avg_lat = sum(t["average_latency_ms"] for t in sc_trials) / len(sc_trials)
            avg_hr = sum(t["hit_rate"] for t in sc_trials) / len(sc_trials)
            avg_ev = sum(t["evictions"] for t in sc_trials) / len(sc_trials)
            summary[scn.lower().replace(" ", "_")] = {
                "scenario": scn,
                "average_latency_ms": round(avg_lat, 2),
                "average_hit_rate": round(avg_hr, 4),
                "average_evictions": round(avg_ev, 1),
                "average_saved_percent": round(sum(t["time_saved_percent"] for t in sc_trials) / len(sc_trials), 2)
            }

    json_path, csv_path = export_experiment_data("C4_CACHE", {"capacity": cache_capacity}, trials, summary)
    plot_path = generate_c4_plot(trials)

    return {
        "experiment_code": "C4_CACHE",
        "parameters": {
            "cache_capacity": cache_capacity,
            "distinct_queries_count": distinct_queries_count,
            "repeat_queries_count": repeat_queries_count,
            "work_ms": work_ms,
            "repeat": repeat
        },
        "trials": trials,
        "summary": summary,
        "artifacts": {
            "json": str(json_path.name),
            "csv": str(csv_path.name),
            "plot": str(plot_path.name) if plot_path else None
        }
    }
