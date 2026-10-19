"""Serviço de coleta e cálculo de métricas do sistema e do processo.

Distingue métricas instantâneas de métricas acumuladas e documenta limitações
técnicas de observabilidade impostas pelo sistema operacional.
"""

import os
import resource
import threading
import time
from typing import Any, Dict, Optional
import psutil

# Controle de requisições e estado global da aplicação
_app_start_time = time.time()
_request_counter_lock = threading.Lock()
_total_requests = 0


def record_request() -> None:
    """Incrementa de forma thread-safe o contador de requisições processadas."""
    global _total_requests
    with _request_counter_lock:
        _total_requests += 1


def get_total_requests() -> int:
    """Retorna o total acumulado de requisições."""
    with _request_counter_lock:
        return _total_requests


def get_page_faults() -> Dict[str, int]:
    """
    Obtém contadores reais de faltas de página (minor e major faults) do processo
    usando resource.getrusage(resource.RUSAGE_SELF).
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "minor_faults": usage.ru_minflt,  # Faltas leves (resolvidas em memória/cache de páginas)
        "major_faults": usage.ru_majflt   # Faltas graves (exigiram I/O de armazenamento ou swap)
    }


def get_system_metrics() -> Dict[str, Any]:
    """
    Retorna métricas divididas estritamente entre instantâneas e acumuladas,
    além de documentar limitações de observabilidade.
    """
    current_process = psutil.Process(os.getpid())
    
    # 1. Métricas Instantâneas (Snapshot no momento da requisição)
    mem_info = current_process.memory_info()
    sys_mem = psutil.virtual_memory()
    sys_swap = psutil.swap_memory()
    
    # Tentativa de listar descritores de arquivos abertos pelo processo
    try:
        open_files_count = len(current_process.open_files())
    except Exception:
        open_files_count = None

    instantaneous: Dict[str, Any] = {
        "timestamp_unix": time.time(),
        "process": {
            "pid": current_process.pid,
            "threads_count": current_process.num_threads(),
            "cpu_percent": current_process.cpu_percent(interval=None),
            "memory_rss_bytes": mem_info.rss,
            "memory_rss_mb": round(mem_info.rss / (1024 * 1024), 2),
            "memory_vsz_bytes": mem_info.vms,
            "memory_vsz_mb": round(mem_info.vms / (1024 * 1024), 2),
            "open_files_count": open_files_count
        },
        "system_global": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_available_bytes": sys_mem.available,
            "memory_available_mb": round(sys_mem.available / (1024 * 1024), 2),
            "memory_percent_used": sys_mem.percent,
            "swap_used_bytes": sys_swap.used,
            "swap_used_mb": round(sys_swap.used / (1024 * 1024), 2),
            "swap_percent_used": sys_swap.percent
        }
    }
    
    # 2. Métricas Acumuladas (Desde a inicialização do processo ou sistema)
    cpu_times = current_process.cpu_times()
    uptime_seconds = time.time() - _app_start_time
    page_faults = get_page_faults()
    
    # Contadores de I/O de processo (disponível em Linux via /proc/[pid]/io)
    try:
        io_counters = current_process.io_counters()
        io_metrics = {
            "read_count": io_counters.read_count,
            "write_count": io_counters.write_count,
            "read_bytes": io_counters.read_bytes,
            "read_mb": round(io_counters.read_bytes / (1024 * 1024), 2),
            "write_bytes": io_counters.write_bytes,
            "write_mb": round(io_counters.write_bytes / (1024 * 1024), 2)
        }
    except Exception:
        io_metrics = {
            "read_count": None,
            "write_count": None,
            "read_bytes": None,
            "write_bytes": None,
            "note": "Contadores de I/O por processo inacessíveis neste ambiente"
        }

    accumulated: Dict[str, Any] = {
        "uptime_seconds": round(uptime_seconds, 2),
        "total_http_requests": get_total_requests(),
        "process_cpu_time": {
            "user_seconds": round(cpu_times.user, 3),
            "system_seconds": round(cpu_times.system, 3),
            "total_seconds": round(cpu_times.user + cpu_times.system, 3)
        },
        "page_faults": page_faults,
        "io_counters": io_metrics
    }
    
    # 3. Limitações Técnicas Documentadas
    limitations = [
        "Page faults coletados via resource.getrusage refletem todo o processo (agregado das threads), "
        "não sendo granularmente rastreáveis por thread sem auxílio de eBPF ou perf.",
        "Contadores de I/O em /proc/[pid]/io reportam chamadas das funções de biblioteca padrão. "
        "Dados lidos ou escritos podem ter sido atendidos ou retidos pelo Page Cache do kernel antes do disco físico.",
        "CPU percent instantâneo depende do intervalo de amostragem; chamadas repetidas sem intervalo "
        "podem retornar 0.0 caso não haja diferença de tick entre coletas consecutivas."
    ]
    
    return {
        "instantaneous": instantaneous,
        "accumulated": accumulated,
        "observability_limitations": limitations
    }
