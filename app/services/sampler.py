"""Mecanismo de Amostragem Temporal de Métricas de SO Durante Experimentos.

Permite coleta controlada:
- Snapshot pontual ("before" / "after").
- Amostragem contínua em background com thread dedicada durante a execução de cada trial ("during").
- Registro com identificadores (experiment_code, run_id, sample_index, timestamp_unix, pid, fase).
- Persistência estruturada em SQLite e exportação para CSV e JSON.
"""

import csv
import json
import os
import resource
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
import psutil

from app.config import CSV_RESULTS_DIR, JSON_RESULTS_DIR
from app.services.linux_metrics import read_proc_meminfo
from app.services.storage import get_metric_samples, save_metric_samples_batch

_sampler_lock = threading.Lock()


def capture_metric_snapshot(
    experiment_code: str,
    run_id: int,
    phase: str = "point_in_time",
    sample_index: int = 0
) -> Dict[str, Any]:
    """
    Captura um instantâneo rigoroso de métricas do processo e do sistema.
    
    Campos indisponíveis são preenchidos com None e documentados explicitamente.
    """
    now = time.time()
    pid = os.getpid()
    proc = psutil.Process(pid)

    # 1. Métricas do Processo
    mem_info = proc.memory_info()
    rusage = resource.getrusage(resource.RUSAGE_SELF)

    # Contadores de I/O em /proc/[pid]/io
    proc_io = {}
    io_file = Path(f"/proc/{pid}/io")
    if io_file.exists():
        try:
            with open(io_file, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.strip().split(":", 1)
                        proc_io[k.strip()] = int(v.strip())
        except Exception:
            pass

    # 2. Métricas Globais do Sistema via /proc/meminfo
    meminfo = read_proc_meminfo()
    mem_sum = meminfo.get("summary", {})

    metrics_payload = {
        # Processo
        "process_rss_mb": round(mem_info.rss / (1024 * 1024), 2),
        "process_vsz_mb": round(mem_info.vms / (1024 * 1024), 2),
        "process_cpu_percent": proc.cpu_percent(interval=None),
        "process_num_threads": proc.num_threads(),
        "process_minor_page_faults": rusage.ru_minflt,
        "process_major_page_faults": rusage.ru_majflt,
        "process_io_rchar": proc_io.get("rchar"),
        "process_io_wchar": proc_io.get("wchar"),
        "process_io_read_bytes": proc_io.get("read_bytes"),
        "process_io_write_bytes": proc_io.get("write_bytes"),
        # Sistema
        "system_mem_total_mb": mem_sum.get("mem_total_mb"),
        "system_mem_free_mb": mem_sum.get("mem_free_mb"),
        "system_mem_available_mb": mem_sum.get("mem_available_mb"),
        "system_cached_mb": mem_sum.get("cached_mb"),
        "system_buffers_mb": mem_sum.get("buffers_mb"),
        "system_swap_used_mb": mem_sum.get("swap_used_mb"),
        "system_cpu_percent": psutil.cpu_percent(interval=None)
    }

    units_catalog = {
        "process_rss_mb": "MB",
        "process_vsz_mb": "MB",
        "process_cpu_percent": "%",
        "process_num_threads": "count",
        "process_minor_page_faults": "count",
        "process_major_page_faults": "count",
        "process_io_rchar": "bytes (chamadas read no user-space)",
        "process_io_wchar": "bytes (chamadas write no user-space)",
        "process_io_read_bytes": "bytes (lidos efetivamente da camada de armazenamento)",
        "process_io_write_bytes": "bytes (enviados efetivamente ao armazenamento)",
        "system_mem_total_mb": "MB",
        "system_mem_free_mb": "MB",
        "system_mem_available_mb": "MB",
        "system_cached_mb": "MB",
        "system_buffers_mb": "MB",
        "system_swap_used_mb": "MB",
        "system_cpu_percent": "%"
    }

    return {
        "experiment_code": experiment_code,
        "run_id": run_id,
        "phase": phase,
        "sample_index": sample_index,
        "timestamp_unix": round(now, 4),
        "pid": pid,
        "source": "/proc/[pid]/io, /proc/meminfo, resource.getrusage, psutil",
        "state": "success",
        "units": units_catalog,
        "metrics": metrics_payload
    }


class ExperimentSamplerSession:
    """Sessão de amostragem de métricas durante um experimento."""

    def __init__(self, experiment_code: str, run_id: int, interval_sec: float = 0.15):
        self.experiment_code = experiment_code
        self.run_id = run_id
        self.interval_sec = interval_sec
        self.samples: List[Dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._sampling_thread: Optional[threading.Thread] = None
        self._sample_counter = 0

    def _sampling_worker(self) -> None:
        """Loop de amostragem contínua durante a fase 'during'."""
        while not self._stop_event.is_set():
            time.sleep(self.interval_sec)
            if self._stop_event.is_set():
                break
            self._sample_counter += 1
            sample = capture_metric_snapshot(
                self.experiment_code,
                self.run_id,
                phase="during",
                sample_index=self._sample_counter
            )
            self.samples.append(sample)

    def start(self) -> None:
        """Inicia a sessão capturando amostra inicial 'before' e disparando o thread de amostragem."""
        self._sample_counter = 0
        before_sample = capture_metric_snapshot(
            self.experiment_code,
            self.run_id,
            phase="before",
            sample_index=0
        )
        self.samples.append(before_sample)

        self._stop_event.clear()
        self._sampling_thread = threading.Thread(
            target=self._sampling_worker,
            name=f"Sampler-{self.experiment_code}-{self.run_id}",
            daemon=True
        )
        self._sampling_thread.start()

    def stop(self) -> List[Dict[str, Any]]:
        """Encerra a amostragem, captura amostra final 'after' e persiste as amostras."""
        self._stop_event.set()
        if self._sampling_thread and self._sampling_thread.is_alive():
            self._sampling_thread.join(timeout=1.0)

        self._sample_counter += 1
        after_sample = capture_metric_snapshot(
            self.experiment_code,
            self.run_id,
            phase="after",
            sample_index=self._sample_counter
        )
        self.samples.append(after_sample)

        # Persistência em lote no SQLite
        save_metric_samples_batch(self.samples)

        return self.samples


@contextmanager
def sample_experiment(
    experiment_code: str,
    run_id: int,
    interval_sec: float = 0.15
) -> Generator[ExperimentSamplerSession, None, None]:
    """
    Context manager para envolver a execução de um trial de experimento com amostragem automática:
    - Captura amostra 'before'
    - Coleta amostras periódicas 'during'
    - Captura amostra 'after'
    - Salva atomicamente no SQLite
    """
    session = ExperimentSamplerSession(experiment_code, run_id, interval_sec=interval_sec)
    session.start()
    try:
        yield session
    finally:
        session.stop()


def export_experiment_samples(experiment_code: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Exporta todas as amostras persistidas de um experimento para arquivos CSV e JSON dedicados.
    
    Salva em:
    - results/csv/{experiment_code.lower()}_samples.csv
    - results/json/{experiment_code.lower()}_samples.json
    Preserva intactos os arquivos brutos anteriores dos experimentos.
    """
    code_normalized = experiment_code.upper()
    samples = get_metric_samples(code_normalized, limit=5000)
    if not samples:
        return None, None

    base_name = f"{experiment_code.lower()}_samples"
    json_path = JSON_RESULTS_DIR / f"{base_name}.json"
    csv_path = CSV_RESULTS_DIR / f"{base_name}.csv"

    # Exporta JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)

    # Exporta CSV tabular com colunas achatadas
    rows_to_write = []
    for s in samples:
        flat_row = {
            "id": s["id"],
            "experiment_code": s["experiment_code"],
            "run_id": s["run_id"],
            "phase": s["phase"],
            "sample_index": s["sample_index"],
            "timestamp_unix": s["timestamp_unix"],
            "pid": s["pid"],
            "source": s["source"],
            "created_at": s["created_at"]
        }
        for k, v in s.get("metrics", {}).items():
            flat_row[k] = v if v is not None else ""
        rows_to_write.append(flat_row)

    if rows_to_write:
        fieldnames = list(rows_to_write[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_to_write)

    return json_path, csv_path
