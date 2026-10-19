"""Serviço de coleta de informações do ambiente operacional e de hardware."""

import os
import platform
import subprocess
import sys
from typing import Any, Dict, Optional
import httpx
import psutil

from app.config import OLLAMA_BASE_URL
from app.services.linux_metrics import (
    read_gpu_detailed_metrics,
    read_os_distribution_info,
    read_proc_cpuinfo,
    read_proc_meminfo,
    read_storage_and_filesystems
)


def get_gpu_info() -> Dict[str, Any]:
    """Obtém informações da GPU NVIDIA via nvidia-smi se disponível."""
    return read_gpu_detailed_metrics()


def check_ollama_service() -> Dict[str, Any]:
    """Verifica se o serviço local do Ollama está acessível e quais modelos estão disponíveis."""
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            models = [m.get("name") for m in data.get("models", [])]
            return {
                "available": True,
                "endpoint": OLLAMA_BASE_URL,
                "models": models
            }
    except Exception as e:
        return {
            "available": False,
            "endpoint": OLLAMA_BASE_URL,
            "models": [],
            "error": f"Ollama inacessível em {OLLAMA_BASE_URL}: {type(e).__name__}"
        }
    return {
        "available": False,
        "endpoint": OLLAMA_BASE_URL,
        "models": [],
        "error": "Resposta inesperada do Ollama"
    }


def get_system_info() -> Dict[str, Any]:
    """
    Coleta informações observáveis reais do sistema operacional, hardware e runtime.
    """
    virtual_mem = psutil.virtual_memory()
    swap_mem = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    
    # Informações de CPU
    cpu_freq = psutil.cpu_freq()
    cpu_details = read_proc_cpuinfo()
    os_distro = read_os_distribution_info()
    meminfo = read_proc_meminfo()
    mem_sum = meminfo.get("summary", {})
    
    # Kernel e SO
    kernel_version = platform.release()
    system_name = platform.system()
    distro_desc = platform.platform()
    
    info: Dict[str, Any] = {
        "operating_system": {
            "system": system_name,
            "kernel": kernel_version,
            "platform": distro_desc,
            "architecture": platform.machine(),
            "distribution": os_distro.get("pretty_name") or os_distro.get("name"),
            "distro_id": os_distro.get("id"),
            "distro_version_id": os_distro.get("version_id"),
            "distro_codename": os_distro.get("version_codename"),
            "source": "/etc/os-release e platform"
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "compiler": platform.python_compiler()
        },
        "cpu": {
            "model_name": cpu_details.get("model_name"),
            "vendor_id": cpu_details.get("vendor_id"),
            "cache_size": cpu_details.get("cache_size"),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cpus": psutil.cpu_count(logical=True),
            "current_freq_mhz": round(cpu_freq.current, 2) if cpu_freq else None,
            "min_freq_mhz": round(cpu_freq.min, 2) if cpu_freq and cpu_freq.min else None,
            "max_freq_mhz": round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None,
            "flags_sample": cpu_details.get("flags_sample", []),
            "source": "/proc/cpuinfo e psutil"
        },
        "memory_ram": {
            "total_bytes": virtual_mem.total,
            "total_gb": round(virtual_mem.total / (1024 ** 3), 2),
            "available_bytes": virtual_mem.available,
            "available_gb": round(virtual_mem.available / (1024 ** 3), 2),
            "free_bytes": virtual_mem.free,
            "free_gb": round(virtual_mem.free / (1024 ** 3), 2),
            "buffers_mb": mem_sum.get("buffers_mb"),
            "cached_mb": mem_sum.get("cached_mb"),
            "percent_used": virtual_mem.percent,
            "source": "/proc/meminfo e psutil"
        },
        "memory_swap": {
            "total_bytes": swap_mem.total,
            "total_gb": round(swap_mem.total / (1024 ** 3), 2),
            "used_bytes": swap_mem.used,
            "used_gb": round(swap_mem.used / (1024 ** 3), 2),
            "free_bytes": swap_mem.free,
            "free_gb": round(swap_mem.free / (1024 ** 3), 2),
            "percent_used": swap_mem.percent,
            "source": "/proc/meminfo e psutil"
        },
        "storage_root": {
            "total_bytes": disk.total,
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "free_bytes": disk.free,
            "free_gb": round(disk.free / (1024 ** 3), 2),
            "percent_used": disk.percent,
            "source": "psutil.disk_usage"
        },
        "gpu": get_gpu_info(),
        "ollama_runtime": check_ollama_service()
    }
    
    return info
