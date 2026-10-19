"""Experimento C6: Tolerância a Falhas e Recuperação (Retentativa, Descarte e Saturação)."""

import time
from typing import Any, Dict, List, Optional
import psutil

from app.config import DEFAULT_QUEUE_MAXSIZE, DEFAULT_WORKERS_COUNT
from app.experiments.reporting import export_experiment_data, generate_c6_plot
from app.services.request_queue import QueueFullError, TaskStatus, task_queue_manager
from app.services.storage import save_experiment_run


def run_fault_experiment(
    faulty_tasks_count: int = 10,
    healthy_tasks_count: int = 10,
    max_retries: int = 2,
    repeat: int = 3
) -> Dict[str, Any]:
    """
    Executa o experimento C6 avaliando a robustez do sistema diante de falhas controladas:
    1. Cenário A: Falhas transitórias recuperadas via Política de Retentativa (Retry).
    2. Cenário B: Falhas persistentes que excedem retentativas (Descarte seguro sem travamento de workers).
    3. Cenário C: Saturação da fila compartilhada (Backpressure) e teste de continuidade do serviço.
    """
    original_capacity = task_queue_manager.maxsize
    original_workers = len(task_queue_manager._workers) or DEFAULT_WORKERS_COUNT

    trials: List[Dict[str, Any]] = []
    trial_id = 1

    try:
        # Garante 2 workers para o teste de resiliência
        task_queue_manager.scale_workers(2)

        for rep in range(repeat):
            # -------------------------------------------------------------
            # Cenário 1: Falhas Transitórias com Retentativa Bem-Sucedida
            # -------------------------------------------------------------
            start_time = time.perf_counter_ns()
            submitted_ids = []

            for i in range(faulty_tasks_count):
                rec = task_queue_manager.submit_task(
                    task_type="fault_test",
                    payload={
                        "should_fail": True,
                        "fail_attempts": 1,     # Falha na 1ª tentativa, sucede na 2ª
                        "max_retries": max_retries,
                        "error_message": f"Erro transitório de simulação #{i+1}"
                    }
                )
                submitted_ids.append(rec.task_id)

            task_queue_manager.wait_completion(timeout=15.0)
            duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

            success_count = 0
            recovered_count = 0
            failed_count = 0

            for tid in submitted_ids:
                info = task_queue_manager.get_task(tid)
                if info:
                    if info["status"] == TaskStatus.COMPLETED.value:
                        success_count += 1
                        if info.get("result", {}).get("recovered"):
                            recovered_count += 1
                    elif info["status"] == TaskStatus.FAILED.value:
                        failed_count += 1

            t1 = {
                "run_id": trial_id,
                "repetition": rep + 1,
                "scenario_name": "Falhas Transitórias (Retry)",
                "faults_injected": faulty_tasks_count,
                "max_retries_configured": max_retries,
                "success_tasks": success_count,
                "recovered_tasks": recovered_count,
                "failed_tasks": failed_count,
                "duration_ms": round(duration_ms, 2),
                "workers_survived": len(task_queue_manager._workers),
                "queue_consistent": task_queue_manager._queue.empty()
            }
            trials.append(t1)
            save_experiment_run("EXP_C6_FAULT", trial_id, {"scenario": "transient_faults", "rep": rep + 1}, t1)
            trial_id += 1

            # -------------------------------------------------------------
            # Cenário 2: Falhas Persistentes (Descarte Seguro sem Quebra do Pool)
            # -------------------------------------------------------------
            start_time = time.perf_counter_ns()
            submitted_ids = []

            for i in range(faulty_tasks_count):
                rec = task_queue_manager.submit_task(
                    task_type="fault_test",
                    payload={
                        "should_fail": True,
                        "fail_attempts": 10,    # Sempre falha além do limite de retentativas
                        "max_retries": 1,
                        "error_message": f"Erro fatal controlado #{i+1}"
                    }
                )
                submitted_ids.append(rec.task_id)

            task_queue_manager.wait_completion(timeout=15.0)
            duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

            failed_count = 0
            for tid in submitted_ids:
                info = task_queue_manager.get_task(tid)
                if info and info["status"] == TaskStatus.FAILED.value:
                    failed_count += 1

            t2 = {
                "run_id": trial_id,
                "repetition": rep + 1,
                "scenario_name": "Falhas Persistentes (Descarte)",
                "faults_injected": faulty_tasks_count,
                "max_retries_configured": 1,
                "success_tasks": 0,
                "recovered_tasks": 0,
                "failed_tasks": failed_count,
                "duration_ms": round(duration_ms, 2),
                "workers_survived": len(task_queue_manager._workers),
                "queue_consistent": task_queue_manager._queue.empty()
            }
            trials.append(t2)
            save_experiment_run("EXP_C6_FAULT", trial_id, {"scenario": "permanent_faults", "rep": rep + 1}, t2)
            trial_id += 1

            # -------------------------------------------------------------
            # Cenário 3: Saturação de Fila e Continuidade do Serviço
            # -------------------------------------------------------------
            # Reduz a capacidade temporariamente para induzir sobrecarga imediata
            task_queue_manager.set_queue_capacity(5)
            saturations_observed = 0
            submitted_saturate = []

            start_time = time.perf_counter_ns()
            for i in range(15):
                try:
                    rec = task_queue_manager.submit_task(
                        task_type="benchmark_task",
                        payload={"work_ms": 10.0, "index": i},
                        timeout=0.05  # Timeout curto para simular rejeição rápida em sobrecarga
                    )
                    submitted_saturate.append(rec.task_id)
                except QueueFullError:
                    saturations_observed += 1

            task_queue_manager.wait_completion(timeout=10.0)

            # Teste de continuidade: submete uma tarefa saudável e verifica execução
            probe = task_queue_manager.submit_task(
                task_type="benchmark_task",
                payload={"work_ms": 5.0, "index": 999},
                timeout=5.0
            )
            task_queue_manager.wait_completion(timeout=5.0)
            probe_info = task_queue_manager.get_task(probe.task_id)
            service_continued = probe_info is not None and probe_info["status"] == TaskStatus.COMPLETED.value
            duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

            # Restaura capacidade
            task_queue_manager.set_queue_capacity(original_capacity)

            t3 = {
                "run_id": trial_id,
                "repetition": rep + 1,
                "scenario_name": "Saturação de Fila",
                "faults_injected": saturations_observed,
                "max_retries_configured": 0,
                "success_tasks": len(submitted_saturate) + (1 if service_continued else 0),
                "recovered_tasks": 0,
                "failed_tasks": saturations_observed,
                "duration_ms": round(duration_ms, 2),
                "workers_survived": len(task_queue_manager._workers),
                "queue_consistent": service_continued
            }
            trials.append(t3)
            save_experiment_run("EXP_C6_FAULT", trial_id, {"scenario": "queue_saturation", "rep": rep + 1}, t3)
            trial_id += 1

    finally:
        task_queue_manager.set_queue_capacity(original_capacity)
        task_queue_manager.scale_workers(original_workers)

    summary: Dict[str, Any] = {}
    for scn in ["Falhas Transitórias (Retry)", "Falhas Persistentes (Descarte)", "Saturação de Fila"]:
        sc_trials = [t for t in trials if t["scenario_name"] == scn]
        if sc_trials:
            summary[scn.lower().replace(" ", "_").replace("(", "").replace(")", "")] = {
                "scenario": scn,
                "average_success_tasks": round(sum(t["success_tasks"] for t in sc_trials) / len(sc_trials), 1),
                "average_recovered_tasks": round(sum(t["recovered_tasks"] for t in sc_trials) / len(sc_trials), 1),
                "average_failed_tasks": round(sum(t["failed_tasks"] for t in sc_trials) / len(sc_trials), 1),
                "all_workers_survived": all(t["workers_survived"] >= 2 for t in sc_trials),
                "queue_consistency_preserved": all(t["queue_consistent"] for t in sc_trials)
            }

    json_path, csv_path = export_experiment_data("C6_FAULT", {"faulty_count": faulty_tasks_count}, trials, summary)
    plot_path = generate_c6_plot(trials)

    return {
        "experiment_code": "C6_FAULT",
        "parameters": {
            "faulty_tasks_count": faulty_tasks_count,
            "healthy_tasks_count": healthy_tasks_count,
            "max_retries": max_retries,
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
