"""Experimento C3: Concorrência e Escalabilidade na Fila Compartilhada (1, 2 e 4 Workers)."""

import os
import resource
import time
from typing import Any, Dict, List, Optional
import psutil

from app.config import DEFAULT_WORKERS_COUNT
from app.experiments.reporting import export_experiment_data, generate_c3_plot
from app.services.request_queue import task_queue_manager
from app.services.sampler import export_experiment_samples, sample_experiment
from app.services.storage import save_experiment_run


def run_concurrency_experiment(
    workers_list: Optional[List[int]] = None,
    tasks_per_trial: int = 20,
    queue_capacity: int = 10,
    work_ms: float = 15.0,
    repeat: int = 3
) -> Dict[str, Any]:
    """
    Executa o benchmark C3 comparando o desempenho da fila compartilhada com 1, 2 e 4 workers.
    """
    if workers_list is None:
        workers_list = [1, 2, 4]

    original_capacity = task_queue_manager.maxsize
    original_workers = len(task_queue_manager._workers) or DEFAULT_WORKERS_COUNT
    process = psutil.Process()

    trials: List[Dict[str, Any]] = []
    trial_id = 1

    try:
        # Configura capacidade da fila para o experimento
        task_queue_manager.set_queue_capacity(queue_capacity)

        for w_count in workers_list:
            for rep in range(repeat):
                # Ajusta quantidade de workers ativos
                task_queue_manager.scale_workers(w_count)
                time.sleep(0.1)  # Estabilização das threads

                with sample_experiment("C3_CONCURRENCY", trial_id, interval_sec=0.03):
                    cpu_before = psutil.cpu_percent(interval=None)
                    rss_before = process.memory_info().rss
                    start_time = time.perf_counter_ns()

                    submitted_ids: List[str] = []
                    queue_full_blocks = 0

                    # Submete as tarefas
                    for i in range(tasks_per_trial):
                        try:
                            record = task_queue_manager.submit_task(
                                task_type="benchmark_task",
                                payload={
                                    "work_ms": work_ms,
                                    "iterations": 3000,
                                    "index": i
                                },
                                timeout=5.0
                            )
                            submitted_ids.append(record.task_id)
                        except Exception:
                            queue_full_blocks += 1

                    # Aguarda todas as tarefas completarem
                    completed_cleanly = task_queue_manager.wait_completion(timeout=30.0)
                    duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

                    rss_after = process.memory_info().rss
                    cpu_after = psutil.cpu_percent(interval=None)

                # Coleta tempos de cada tarefa
                wait_times: List[float] = []
                exec_times: List[float] = []
                latencies: List[float] = []

                for tid in submitted_ids:
                    t_info = task_queue_manager.get_task(tid)
                    if t_info and t_info.get("timing"):
                        w_ms = t_info["timing"].get("wait_time_ms")
                        e_ms = t_info["timing"].get("execution_time_ms")
                        tot_ms = t_info["timing"].get("total_time_ms")
                        if w_ms is not None:
                            wait_times.append(w_ms)
                        if e_ms is not None:
                            exec_times.append(e_ms)
                        if tot_ms is not None:
                            latencies.append(tot_ms)

                completed_count = len(latencies)
                throughput = (completed_count / (duration_ms / 1000.0)) if duration_ms > 0 else 0.0
                avg_latency = (sum(latencies) / completed_count) if completed_count > 0 else 0.0
                avg_wait = (sum(wait_times) / completed_count) if completed_count > 0 else 0.0
                avg_exec = (sum(exec_times) / completed_count) if completed_count > 0 else 0.0

                trial_record = {
                    "run_id": trial_id,
                    "repetition": rep + 1,
                    "workers": w_count,
                    "tasks_submitted": tasks_per_trial,
                    "tasks_completed": completed_count,
                    "queue_capacity": queue_capacity,
                    "duration_ms": round(duration_ms, 2),
                    "throughput_tasks_per_sec": round(throughput, 2),
                    "average_latency_ms": round(avg_latency, 2),
                    "average_wait_time_ms": round(avg_wait, 2),
                    "average_exec_time_ms": round(avg_exec, 2),
                    "queue_full_blocks": queue_full_blocks,
                    "rss_before_mb": round(rss_before / (1024 * 1024), 2),
                    "rss_after_mb": round(rss_after / (1024 * 1024), 2),
                    "completed_within_timeout": completed_cleanly
                }
                trials.append(trial_record)

                save_experiment_run(
                    experiment_code="EXP_C3_CONCURRENCY",
                    run_id=trial_id,
                    parameters={"workers": w_count, "tasks": tasks_per_trial, "capacity": queue_capacity},
                    metrics=trial_record
                )
                trial_id += 1

    finally:
        # Restaura configuração original da fila
        task_queue_manager.set_queue_capacity(original_capacity)
        task_queue_manager.scale_workers(original_workers)

    # Sumário agrupado por quantidade de workers
    summary: Dict[str, Any] = {}
    for w in workers_list:
        w_trials = [t for t in trials if t["workers"] == w]
        if w_trials:
            avg_tp = sum(t["throughput_tasks_per_sec"] for t in w_trials) / len(w_trials)
            avg_lat = sum(t["average_latency_ms"] for t in w_trials) / len(w_trials)
            avg_wait = sum(t["average_wait_time_ms"] for t in w_trials) / len(w_trials)
            summary[f"{w}_workers"] = {
                "average_throughput_tasks_sec": round(avg_tp, 2),
                "average_latency_ms": round(avg_lat, 2),
                "average_queue_wait_ms": round(avg_wait, 2),
                "speedup_vs_1_worker": (
                    round(avg_tp / (summary.get("1_workers", {}).get("average_throughput_tasks_sec") or avg_tp), 2)
                    if "1_workers" in summary else 1.0
                )
            }

    json_path, csv_path = export_experiment_data("C3_CONCURRENCY", {"workers": workers_list, "tasks": tasks_per_trial}, trials, summary)
    plot_path = generate_c3_plot(trials)
    samples_json, samples_csv = export_experiment_samples("C3_CONCURRENCY")

    return {
        "experiment_code": "C3_CONCURRENCY",
        "parameters": {
            "workers_list": workers_list,
            "tasks_per_trial": tasks_per_trial,
            "queue_capacity": queue_capacity,
            "work_ms": work_ms,
            "repeat": repeat
        },
        "trials": trials,
        "summary": summary,
        "artifacts": {
            "json": str(json_path.name),
            "csv": str(csv_path.name),
            "plot": str(plot_path.name) if plot_path else None,
            "samples_csv": str(samples_csv.name) if samples_csv else None,
            "samples_json": str(samples_json.name) if samples_json else None
        }
    }
