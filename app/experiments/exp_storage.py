"""Experimentos C1 e C2: Leitura Convencional de Arquivos vs Mapeamento de Memória (mmap)."""

import mmap
import os
import resource
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import psutil

from app.config import CORPUS_DIR, DATA_DIR
from app.experiments.reporting import export_experiment_data, generate_c1_c2_plot
from app.services.storage import save_experiment_run

# Arquivo padrão para os testes de armazenamento
DEFAULT_STORAGE_TEST_FILE = DATA_DIR / "storage_benchmark_sample.bin"


def ensure_storage_benchmark_file(target_size_mb: int = 10) -> Path:
    """
    Garante a existência de um arquivo binário estruturado com tamanho conhecido
    para comparação reprodutiva entre read() e mmap().
    """
    if DEFAULT_STORAGE_TEST_FILE.exists():
        actual_size = DEFAULT_STORAGE_TEST_FILE.stat().st_size
        if actual_size >= target_size_mb * 1024 * 1024:
            return DEFAULT_STORAGE_TEST_FILE

    # Gera arquivo determinístico com blocos de 64 KiB
    block_size = 64 * 1024
    total_blocks = (target_size_mb * 1024 * 1024) // block_size
    pattern = (b"GenResearchOSBenchBlock0123456789ABCDEF" * (block_size // 40))[:block_size]

    with open(DEFAULT_STORAGE_TEST_FILE, "wb") as f:
        for _ in range(total_blocks):
            f.write(pattern)

    return DEFAULT_STORAGE_TEST_FILE


def _read_conventional(file_path: Path, chunk_size: int = 64 * 1024) -> Tuple[int, float, int, int]:
    """
    Executa leitura convencional utilizando open() e read() em blocos.
    Retorna: (total_bytes_lidos, duracao_ms, minor_faults_delta, major_faults_delta)
    """
    rusage_before = resource.getrusage(resource.RUSAGE_SELF)
    start_time = time.perf_counter_ns()
    total_bytes = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)

    duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0
    rusage_after = resource.getrusage(resource.RUSAGE_SELF)

    minor_faults = rusage_after.ru_minflt - rusage_before.ru_minflt
    major_faults = rusage_after.ru_majflt - rusage_before.ru_majflt

    return total_bytes, duration_ms, minor_faults, major_faults


def _read_mmap(file_path: Path, chunk_size: int = 64 * 1024) -> Tuple[int, float, int, int]:
    """
    Executa leitura por mapeamento de memória utilizando mmap.mmap().
    Retorna: (total_bytes_lidos, duracao_ms, minor_faults_delta, major_faults_delta)
    """
    rusage_before = resource.getrusage(resource.RUSAGE_SELF)
    start_time = time.perf_counter_ns()
    total_bytes = 0

    with open(file_path, "rb") as f:
        file_size = f.seek(0, os.SEEK_END)
        f.seek(0)
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            offset = 0
            while offset < file_size:
                end = min(offset + chunk_size, file_size)
                # Acesso à memória virtual mapeada (desencadeia lazy paging via MMU)
                chunk_slice = mm[offset:end]
                total_bytes += len(chunk_slice)
                offset = end

    duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0
    rusage_after = resource.getrusage(resource.RUSAGE_SELF)

    minor_faults = rusage_after.ru_minflt - rusage_before.ru_minflt
    major_faults = rusage_after.ru_majflt - rusage_before.ru_majflt

    return total_bytes, duration_ms, minor_faults, major_faults


def run_storage_experiment(
    mode: str = "both",  # "conventional", "mmap", "both"
    file_size_mb: int = 10,
    chunk_size_kb: int = 64,
    repeat: int = 3
) -> Dict[str, Any]:
    """
    Executa os experimentos C1 e C2 comparando E/S convencional vs mmap.
    """
    test_file = ensure_storage_benchmark_file(target_size_mb=file_size_mb)
    actual_file_bytes = test_file.stat().st_size
    chunk_size_bytes = chunk_size_kb * 1024

    process = psutil.Process()
    methods_to_test = []
    if mode in ("conventional", "both"):
        methods_to_test.append("conventional")
    if mode in ("mmap", "both"):
        methods_to_test.append("mmap")

    trials: List[Dict[str, Any]] = []
    trial_id = 1

    for method in methods_to_test:
        for rep in range(repeat):
            rss_before = process.memory_info().rss
            if method == "conventional":
                bytes_read, duration_ms, min_flt, maj_flt = _read_conventional(test_file, chunk_size_bytes)
            else:
                bytes_read, duration_ms, min_flt, maj_flt = _read_mmap(test_file, chunk_size_bytes)
            rss_after = process.memory_info().rss

            throughput_mb_s = (bytes_read / (1024 * 1024)) / (duration_ms / 1000.0) if duration_ms > 0 else 0.0

            trial_record = {
                "run_id": trial_id,
                "repetition": rep + 1,
                "method": method,
                "file_size_mb": round(actual_file_bytes / (1024 * 1024), 2),
                "chunk_size_kb": chunk_size_kb,
                "bytes_read": bytes_read,
                "duration_ms": round(duration_ms, 3),
                "throughput_mb_s": round(throughput_mb_s, 2),
                "rss_before_mb": round(rss_before / (1024 * 1024), 2),
                "rss_after_mb": round(rss_after / (1024 * 1024), 2),
                "minor_page_faults": min_flt,
                "major_page_faults": maj_flt
            }
            trials.append(trial_record)

            # Persiste no SQLite
            save_experiment_run(
                experiment_code=f"EXP_{method.upper()}",
                run_id=trial_id,
                parameters={"method": method, "chunk_size_kb": chunk_size_kb, "file_size_mb": file_size_mb},
                metrics=trial_record
            )
            trial_id += 1

    # Estatísticas agregadas
    summary: Dict[str, Any] = {}
    for m in methods_to_test:
        m_trials = [t for t in trials if t["method"] == m]
        avg_dur = sum(t["duration_ms"] for t in m_trials) / len(m_trials)
        avg_tp = sum(t["throughput_mb_s"] for t in m_trials) / len(m_trials)
        avg_min_flt = sum(t["minor_page_faults"] for t in m_trials) / len(m_trials)
        summary[m] = {
            "repetitions": len(m_trials),
            "average_duration_ms": round(avg_dur, 3),
            "average_throughput_mb_s": round(avg_tp, 2),
            "average_minor_faults": round(avg_min_flt, 1),
            "notes": (
                "Dados lidos podem estar em Page Cache do kernel após a primeira iteração."
            )
        }

    # Análise comparativa se ambos forem executados
    if "conventional" in summary and "mmap" in summary:
        dur_conv = summary["conventional"]["average_duration_ms"]
        dur_mmap = summary["mmap"]["average_duration_ms"]
        diff_percent = round(((dur_mmap - dur_conv) / dur_conv) * 100.0, 2) if dur_conv > 0 else 0.0
        summary["comparison"] = {
            "mmap_vs_conventional_duration_diff_percent": diff_percent,
            "interpretation": (
                "mmap evita sobrecargas de cópia de memória entre espaço de kernel e usuário (zero-copy), "
                "mas o desempenho efetivo depende do estado do Page Cache e da granularidade do acesso."
            )
        }

    exp_code = "C1_CONVENTIONAL" if mode == "conventional" else ("C2_MMAP" if mode == "mmap" else "C1_C2_STORAGE")
    json_path, csv_path = export_experiment_data(exp_code, {"mode": mode, "file_size_mb": file_size_mb}, trials, summary)
    plot_path = generate_c1_c2_plot(trials)

    return {
        "experiment_code": exp_code,
        "parameters": {
            "mode": mode,
            "file_size_mb": file_size_mb,
            "chunk_size_kb": chunk_size_kb,
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
