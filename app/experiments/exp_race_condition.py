"""Experimento D: Demonstração e correção de Condição de Corrida (Race Condition).

Compara o comportamento de um contador compartilhado acessado concorrentemente
por múltiplas threads em dois modos:
1. Sem sincronização: atualizações perdidas (lost updates) causadas por chaveamento de contexto.
2. Com sincronização: exclusão mútua garantida via threading.Lock.
"""

import threading
import time
from typing import Any, Dict, List, Optional
import psutil

from app.experiments.reporting import export_experiment_data, generate_race_condition_plot
from app.services.storage import save_experiment_run


class SharedCounter:
    """Contador compartilhado com suporte a incremento desprotegido e protegido."""

    def __init__(self, initial_value: int = 0):
        self.value = initial_value
        self.lock = threading.Lock()

    def increment_unsynchronized(self, inject_interleaving: bool = True) -> None:
        """
        Incremento desprotegido na região crítica (Read-Modify-Write).
        
        A chamada time.sleep(0) força a liberação do GIL e cede a fatia de tempo
        ao escalonador do SO (sched_yield), permitindo demonstrar de forma controlada
        e reproduzível a perda de atualizações quando outra thread lê o valor defasado.
        """
        temp = self.value
        if inject_interleaving:
            time.sleep(0)
        self.value = temp + 1

    def increment_synchronized(self, inject_interleaving: bool = True) -> None:
        """
        Incremento protegido por exclusão mútua via threading.Lock.
        
        Mesmo com a mesma janela de interleaving (time.sleep(0)), o Lock impede
        que qualquer outra thread entre na região crítica até a liberação do recurso.
        """
        with self.lock:
            temp = self.value
            if inject_interleaving:
                time.sleep(0)
            self.value = temp + 1


def _run_single_trial(
    num_threads: int,
    increments_per_thread: int,
    use_lock: bool,
    inject_interleaving: bool = True
) -> Dict[str, Any]:
    """
    Executa uma rodada única do experimento de corrida.
    
    Utiliza uma barreira de sincronização (threading.Barrier) para garantir que
    todas as threads iniciem a execução simultaneamente, maximizando a contenção.
    """
    counter = SharedCounter()
    barrier = threading.Barrier(num_threads)
    threads: List[threading.Thread] = []

    def worker_target() -> None:
        barrier.wait()  # Ponto de largada sincronizado
        for _ in range(increments_per_thread):
            if use_lock:
                counter.increment_synchronized(inject_interleaving)
            else:
                counter.increment_unsynchronized(inject_interleaving)

    for i in range(num_threads):
        t = threading.Thread(target=worker_target, name=f"CounterWorker-{i+1}")
        threads.append(t)
        t.start()

    start_time = time.perf_counter_ns()
    for t in threads:
        t.join()
    duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

    expected = num_threads * increments_per_thread
    observed = counter.value
    lost = expected - observed
    lost_ratio = round((lost / expected) * 100.0, 2) if expected > 0 else 0.0
    ops_per_sec = round((observed / (duration_ms / 1000.0)), 2) if duration_ms > 0 else 0.0

    return {
        "use_lock": use_lock,
        "num_threads": num_threads,
        "increments_per_thread": increments_per_thread,
        "expected_value": expected,
        "observed_value": observed,
        "lost_updates": lost,
        "lost_ratio_percent": lost_ratio,
        "is_correct": (observed == expected),
        "duration_ms": round(duration_ms, 2),
        "operations_per_second": ops_per_sec
    }


def run_race_condition_experiment(
    num_threads: int = 4,
    increments_per_thread: int = 1000,
    mode: str = "both",
    repeat: int = 3,
    inject_interleaving: bool = True
) -> Dict[str, Any]:
    """
    Executa a bateria completa do experimento de condição de corrida.
    
    Parâmetros:
    - num_threads: Quantidade de threads concorrentes competindo pelo contador.
    - increments_per_thread: Número de operações de incremento por thread.
    - mode: 'unsynchronized', 'synchronized' ou 'both' (executa ambos para comparação).
    - repeat: Número de repetições por modo (mínimo 1, recomendado 3 para significância estatística).
    - inject_interleaving: Se True, injeta janela controlada de chaveamento entre leitura e escrita.
    """
    if num_threads < 2:
        raise ValueError("O experimento requer pelo menos 2 threads concorrentes.")
    if increments_per_thread < 1:
        raise ValueError("O número de incrementos por thread deve ser de pelo menos 1.")
    if repeat < 1:
        raise ValueError("O número de repetições deve ser pelo menos 1.")

    modes_to_run = []
    if mode in ("unsynchronized", "both"):
        modes_to_run.append(False)  # False = sem lock
    if mode in ("synchronized", "both"):
        modes_to_run.append(True)   # True = com lock

    trials_results: List[Dict[str, Any]] = []
    trial_counter = 1

    # Snapshot do estado do sistema no início do experimento
    sys_mem = psutil.virtual_memory()
    system_snapshot = {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_available_mb": round(sys_mem.available / (1024 * 1024), 2),
        "active_threads_system": threading.active_count()
    }

    for use_lock in modes_to_run:
        for r in range(repeat):
            trial = _run_single_trial(
                num_threads=num_threads,
                increments_per_thread=increments_per_thread,
                use_lock=use_lock,
                inject_interleaving=inject_interleaving
            )
            trial["run_id"] = trial_counter
            trial["repetition"] = r + 1
            trials_results.append(trial)

            # Persiste no SQLite
            params = {
                "num_threads": num_threads,
                "increments_per_thread": increments_per_thread,
                "use_lock": use_lock,
                "inject_interleaving": inject_interleaving,
                "repetition": r + 1
            }
            save_experiment_run(
                experiment_code="EXP_D_RACE_CONDITION",
                run_id=trial_counter,
                parameters=params,
                metrics=trial,
                system_state=system_snapshot
            )
            trial_counter += 1

    # Análise comparativa
    unsync_trials = [t for t in trials_results if not t["use_lock"]]
    sync_trials = [t for t in trials_results if t["use_lock"]]

    def calc_mode_stats(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not trials:
            return {}
        avg_lost = sum(t["lost_updates"] for t in trials) / len(trials)
        avg_lost_ratio = sum(t["lost_ratio_percent"] for t in trials) / len(trials)
        avg_duration = sum(t["duration_ms"] for t in trials) / len(trials)
        all_correct = all(t["is_correct"] for t in trials)
        return {
            "repetitions": len(trials),
            "all_correct": all_correct,
            "average_lost_updates": round(avg_lost, 2),
            "average_lost_ratio_percent": round(avg_lost_ratio, 2),
            "average_duration_ms": round(avg_duration, 2)
        }

    comparison = {
        "unsynchronized": calc_mode_stats(unsync_trials) if unsync_trials else None,
        "synchronized": calc_mode_stats(sync_trials) if sync_trials else None
    }

    # Análise descritiva
    if unsync_trials and sync_trials:
        avg_unsync_time = comparison["unsynchronized"]["average_duration_ms"]
        avg_sync_time = comparison["synchronized"]["average_duration_ms"]
        overhead_percent = (
            round(((avg_sync_time - avg_unsync_time) / avg_unsync_time) * 100.0, 2)
            if avg_unsync_time > 0 else 0.0
        )
        comparison["trade_off"] = {
            "lock_overhead_percent": overhead_percent,
            "consistency_guarantee": "Exclusão mútua impediu 100% das perdas de atualização registradas no modo desprotegido."
        }

    json_path, csv_path = export_experiment_data(
        "d_race_condition",
        {
            "num_threads": num_threads,
            "increments_per_thread": increments_per_thread,
            "mode": mode,
            "repeat": repeat
        },
        trials_results,
        comparison
    )
    plot_path = generate_race_condition_plot(trials_results)

    return {
        "experiment_code": "EXP_D_RACE_CONDITION",
        "parameters": {
            "num_threads": num_threads,
            "increments_per_thread": increments_per_thread,
            "total_expected_per_run": num_threads * increments_per_thread,
            "mode": mode,
            "repeat": repeat,
            "inject_interleaving": inject_interleaving
        },
        "trials": trials_results,
        "comparison_summary": comparison,
        "artifacts": {
            "json": str(json_path.name),
            "csv": str(csv_path.name),
            "plot": str(plot_path.name) if plot_path else None
        }
    }
