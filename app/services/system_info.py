"""Serviço de coleta de informações do ambiente operacional e de hardware."""

import os
import platform
import subprocess
import sys
from typing import Any, Dict, Optional
import httpx
import psutil

from app.config import OLLAMA_BASE_URL


def get_gpu_info() -> Dict[str, Any]:
    """Obtém informações da GPU NVIDIA via nvidia-smi se disponível."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0
        ).strip()
        if output:
            parts = [p.strip() for p in output.split(",")]
            return {
                "available": True,
                "model": parts[0] if len(parts) > 0 else "Unknown",
                "memory_total_mb": float(parts[1]) if len(parts) > 1 else None,
                "driver_version": parts[2] if len(parts) > 2 else "Unknown"
            }
    except Exception:
        pass
    
    return {
        "available": False,
        "model": None,
        "memory_total_mb": None,
        "driver_version": None,
        "note": "nvidia-smi não disponível ou GPU dedicada não acessível"
    }


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
    
    # Kernel e SO
    kernel_version = platform.release()
    system_name = platform.system()
    distro_desc = platform.platform()
    
    info: Dict[str, Any] = {
        "operating_system": {
            "system": system_name,
            "kernel": kernel_version,
            "platform": distro_desc,
            "architecture": platform.machine()
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "compiler": platform.python_compiler()
        },
        "cpu": {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cpus": psutil.cpu_count(logical=True),
            "current_freq_mhz": round(cpu_freq.current, 2) if cpu_freq else None,
            "min_freq_mhz": round(cpu_freq.min, 2) if cpu_freq and cpu_freq.min else None,
            "max_freq_mhz": round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None
        },
        "memory_ram": {
            "total_bytes": virtual_mem.total,
            "total_gb": round(virtual_mem.total / (1024 ** 3), 2),
            "available_bytes": virtual_mem.available,
            "available_gb": round(virtual_mem.available / (1024 ** 3), 2),
            "free_bytes": virtual_mem.free,
            "free_gb": round(virtual_mem.free / (1024 ** 3), 2),
            "percent_used": virtual_mem.percent
        },
        "memory_swap": {
            "total_bytes": swap_mem.total,
            "total_gb": round(swap_mem.total / (1024 ** 3), 2),
            "used_bytes": swap_mem.used,
            "used_gb": round(swap_mem.used / (1024 ** 3), 2),
            "free_bytes": swap_mem.free,
            "free_gb": round(swap_mem.free / (1024 ** 3), 2),
            "percent_used": swap_mem.percent
        },
        "storage_root": {
            "total_bytes": disk.total,
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "free_bytes": disk.free,
            "free_gb": round(disk.free / (1024 ** 3), 2),
            "percent_used": disk.percent
        },
        "gpu": get_gpu_info(),
        "ollama_runtime": check_ollama_service()
    }
    
    return info
