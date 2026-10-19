"""Experimento C5: Impacto de Memória sob Carga Controlada (RSS, VSZ, Page Faults e Swap)."""

import gc
import resource
import time
from typing import Any, Dict, List, Optional
import psutil

from app.experiments.reporting import export_experiment_data, generate_c5_plot
from app.services.sampler import export_experiment_samples, sample_experiment
from app.services.storage import save_experiment_run

# Margem de segurança mínima no sistema (1 GB livre exigido antes de qualquer alocação)
MIN_SYSTEM_AVAILABLE_HEADROOM_BYTES = 1024 * 1024 * 1024


def run_memory_experiment(
    allocation_steps_mb: Optional[List[int]] = None,
    hold_duration_sec: float = 0.5,
    repeat: int = 3
) -> Dict[str, Any]:
    """
    Executa o experimento C5 com alocações controladas e graduais de memória.
    
    Demonstra conceitos de SO:
    - Diferença entre Espaço Virtual (VSZ) e Memória Residente (RSS).
    - Faltas de página menores (minor page faults) induzidas por lazy allocation do kernel Linux.
    - Efeito da desocupação explícita de páginas e Garbage Collection.
    - Proteção preventiva contra o OOM Killer (Out-Of-Memory Killer).
    """
    if allocation_steps_mb is None:
        allocation_steps_mb = [100, 250, 500]

    process = psutil.Process()
    trials: List[Dict[str, Any]] = []
    trial_id = 1

    for step_mb in allocation_steps_mb:
        for rep in range(repeat):
            # 1. Medições de Pré-alocação
            vm_before = psutil.virtual_memory()
            swap_before = psutil.swap_memory()
            mem_info_before = process.memory_info()
            rusage_before = resource.getrusage(resource.RUSAGE_SELF)

            # Verificação estrita de segurança operacional
            requested_bytes = step_mb * 1024 * 1024
            if vm_before.available < (requested_bytes + MIN_SYSTEM_AVAILABLE_HEADROOM_BYTES):
                trial_record = {
                    "run_id": trial_id,
                    "repetition": rep + 1,
                    "requested_mb": step_mb,
                    "allocated_mb": 0,
                    "aborted_for_safety": True,
                    "reason": "Memória disponível insuficiente para garantir margem de segurança de 1GB."
                }
                trials.append(trial_record)
                trial_id += 1
                continue

            start_time = time.perf_counter_ns()
            allocated_buf: Optional[bytearray] = None
            allocated_successfully = False

            with sample_experiment("C5_MEMORY", trial_id, interval_sec=0.1):
                try:
                    # 2. Alocação e toque nas páginas (page touching a cada 4 KiB)
                    # O toque induz o kernel a alocar quadros físicos na tabela de páginas (Minor Page Faults)
                    allocated_buf = bytearray(requested_bytes)
                    page_size = 4096
                    for offset in range(0, requested_bytes, page_size):
                        allocated_buf[offset] = 0xAA
                    allocated_successfully = True

                    # Medições com a memória ocupada (pico)
                    mem_info_during = process.memory_info()
                    vm_during = psutil.virtual_memory()
                    swap_during = psutil.swap_memory()
                    rusage_during = resource.getrusage(resource.RUSAGE_SELF)

                    # Mantém a alocação pelo tempo especificado
                    time.sleep(hold_duration_sec)

                finally:
                    # 3. Liberação determinística e coleta de lixo
                    if allocated_buf is not None:
                        del allocated_buf
                    gc.collect()

            duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0

            # 4. Medições de Pós-alocação
            mem_info_after = process.memory_info()
            vm_after = psutil.virtual_memory()
            swap_after = psutil.swap_memory()
            rusage_after = resource.getrusage(resource.RUSAGE_SELF)

            minor_faults = rusage_during.ru_minflt - rusage_before.ru_minflt
            major_faults = rusage_during.ru_majflt - rusage_before.ru_majflt

            trial_record = {
                "run_id": trial_id,
                "repetition": rep + 1,
                "requested_mb": step_mb,
                "allocated_successfully": allocated_successfully,
                "duration_ms": round(duration_ms, 2),
                # Métricas do Processo
                "rss_before_mb": round(mem_info_before.rss / (1024 * 1024), 2),
                "rss_during_mb": round(mem_info_during.rss / (1024 * 1024), 2),
                "rss_after_mb": round(mem_info_after.rss / (1024 * 1024), 2),
                "vsz_before_mb": round(mem_info_before.vms / (1024 * 1024), 2),
                "vsz_during_mb": round(mem_info_during.vms / (1024 * 1024), 2),
                "vsz_after_mb": round(mem_info_after.vms / (1024 * 1024), 2),
                # Faltas de Página
                "minor_page_faults": minor_faults,
                "major_page_faults": major_faults,
                # Métricas do Sistema
                "system_total_ram_mb": round(vm_during.total / (1024 * 1024), 2),
                "system_available_ram_mb": round(vm_during.available / (1024 * 1024), 2),
                "swap_used_mb": round(swap_during.used / (1024 * 1024), 2)
            }
            trials.append(trial_record)

            save_experiment_run(
                experiment_code="EXP_C5_MEMORY",
                run_id=trial_id,
                parameters={"requested_mb": step_mb, "rep": rep + 1},
                metrics=trial_record
            )
            trial_id += 1

    # Sumário por patamar de alocação
    summary: Dict[str, Any] = {}
    for step_mb in allocation_steps_mb:
        step_trials = [t for t in trials if t.get("requested_mb") == step_mb and t.get("allocated_successfully")]
        if step_trials:
            avg_peak_rss = sum(t["rss_during_mb"] for t in step_trials) / len(step_trials)
            avg_freed_rss = sum(t["rss_after_mb"] for t in step_trials) / len(step_trials)
            avg_minor = sum(t["minor_page_faults"] for t in step_trials) / len(step_trials)
            summary[f"{step_mb}mb"] = {
                "allocated_mb": step_mb,
                "average_peak_rss_mb": round(avg_peak_rss, 2),
                "average_after_rss_mb": round(avg_freed_rss, 2),
                "average_minor_faults": round(avg_minor, 1),
                "rss_released_efficiently": avg_freed_rss < avg_peak_rss
            }

    json_path, csv_path = export_experiment_data("C5_MEMORY", {"allocation_steps_mb": allocation_steps_mb}, trials, summary)
    plot_path = generate_c5_plot(trials)
    samples_json, samples_csv = export_experiment_samples("C5_MEMORY")

    return {
        "experiment_code": "C5_MEMORY",
        "parameters": {
            "allocation_steps_mb": allocation_steps_mb,
            "hold_duration_sec": hold_duration_sec,
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
