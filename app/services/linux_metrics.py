"""Serviço de Instrumentação do Linux para Coleta de Métricas Reais do Sistema Operacional.

Fontes utilizadas:
- /proc/meminfo (MemFree, MemAvailable, Buffers, Cached, Anon, File, Slab)
- /proc/cpuinfo (Modelo, núcleos, frequência, cache)
- /proc/[pid]/io (rchar, wchar, syscr, syscw, read_bytes, write_bytes)
- /proc/[pid]/stat e resource.getrusage (Minor/Major page faults, RSS, VMS)
- /etc/os-release (Distribuição e versão)
- psutil e /proc/diskstats (Partições, I/O de disco)
- nvidia-smi (GPU dedicada, VRAM, temperatura)

Não utiliza números fictícios: dados indisponíveis são sinalizados explicitamente.
"""

import os
import platform
import resource
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import psutil

from app.config import CORPUS_DIR, DATABASE_PATH, DATA_DIR, RESULTS_DIR, VECTORS_MAP_PATH, VECTORS_NPY_PATH


def read_proc_meminfo() -> Dict[str, Any]:
    """
    Lê e estrutura os dados brutos de /proc/meminfo fornecidos pelo kernel Linux.
    
    Apresenta separadamente:
    - MemFree: Memória física não alocada.
    - MemAvailable: Estimativa da memória disponível para novas aplicações sem provocar swap.
    - Buffers e Cached: Cache de páginas e buffers de blocos de disco.
    - Memória Anônima: Páginas não vinculadas a arquivos (heap, stack, mmap anônimo).
    - Memória de Arquivos: Páginas mapeadas a partir de arquivos (passíveis de descarte limpo).
    """
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return {
            "available": False,
            "source": "/proc/meminfo",
            "error": "Arquivo /proc/meminfo não encontrado neste ambiente."
        }

    raw_values: Dict[str, int] = {}
    with open(meminfo_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val_parts = parts[1].strip().split()
                try:
                    # Valores em /proc/meminfo são tipicamente em kB
                    raw_values[key] = int(val_parts[0])
                except (ValueError, IndexError):
                    pass

    # Conversão segura para bytes e MB
    def _to_bytes(kb_key: str) -> Optional[int]:
        val = raw_values.get(kb_key)
        return (val * 1024) if val is not None else None

    def _to_mb(kb_key: str) -> Optional[float]:
        val = raw_values.get(kb_key)
        return round(val / 1024.0, 2) if val is not None else None

    return {
        "source": "/proc/meminfo",
        "units": "bytes, kibibytes (kB) e megabytes (MB)",
        "summary": {
            "mem_total_mb": _to_mb("MemTotal"),
            "mem_free_mb": _to_mb("MemFree"),
            "mem_available_mb": _to_mb("MemAvailable"),
            "buffers_mb": _to_mb("Buffers"),
            "cached_mb": _to_mb("Cached"),
            "swap_cached_mb": _to_mb("SwapCached"),
            "swap_total_mb": _to_mb("SwapTotal"),
            "swap_free_mb": _to_mb("SwapFree"),
            "swap_used_mb": round((raw_values.get("SwapTotal", 0) - raw_values.get("SwapFree", 0)) / 1024.0, 2)
            if "SwapTotal" in raw_values and "SwapFree" in raw_values else None
        },
        "breakdown": {
            "physical_ram": {
                "mem_total_bytes": _to_bytes("MemTotal"),
                "mem_free_bytes": _to_bytes("MemFree"),
                "mem_available_bytes": _to_bytes("MemAvailable")
            },
            "page_cache_and_buffers": {
                "buffers_bytes": _to_bytes("Buffers"),
                "cached_bytes": _to_bytes("Cached"),
                "swap_cached_bytes": _to_bytes("SwapCached"),
                "dirty_bytes": _to_bytes("Dirty"),
                "writeback_bytes": _to_bytes("Writeback")
            },
            "anonymous_memory": {
                "active_anon_bytes": _to_bytes("Active(anon)"),
                "inactive_anon_bytes": _to_bytes("Inactive(anon)"),
                "anon_pages_bytes": _to_bytes("AnonPages")
            },
            "file_backed_memory": {
                "active_file_bytes": _to_bytes("Active(file)"),
                "inactive_file_bytes": _to_bytes("Inactive(file)")
            },
            "shared_and_kernel": {
                "shmem_bytes": _to_bytes("Shmem"),
                "slab_bytes": _to_bytes("Slab"),
                "s_reclaimable_bytes": _to_bytes("SReclaimable"),
                "s_unreclaim_bytes": _to_bytes("SUnreclaim")
            }
        },
        "operating_system_concepts": {
            "mem_free_vs_available": (
                "MemFree representa páginas de RAM totalmente vazias (ociosas). "
                "MemAvailable representa a memória que pode ser alocada imediatamente por processos sem swap, "
                "pois inclui o Page Cache e SReclaimable que o kernel pode descartar instantaneamente."
            ),
            "page_cache_role": (
                "O Linux utiliza memória livre para manter cópias em RAM de blocos de arquivos acessados recentemente. "
                "Isso acelera dramaticamente leituras posteriores (como em C1 e C2) e não representa falta de memória."
            )
        }
    }


def read_proc_cpuinfo() -> Dict[str, Any]:
    """Lê informações reais de arquitetura e modelo dos processadores a partir de /proc/cpuinfo."""
    cpuinfo_path = Path("/proc/cpuinfo")
    model_name = "Desconhecido"
    vendor_id = "Desconhecido"
    cache_size = "Desconhecido"
    cpu_cores = psutil.cpu_count(logical=False)
    logical_cpus = psutil.cpu_count(logical=True)
    flags_sample = []

    if cpuinfo_path.exists():
        try:
            with open(cpuinfo_path, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        k, v = [x.strip() for x in line.split(":", 1)]
                        if k == "model name" and model_name == "Desconhecido":
                            model_name = v
                        elif k == "vendor_id" and vendor_id == "Desconhecido":
                            vendor_id = v
                        elif k == "cache size" and cache_size == "Desconhecido":
                            cache_size = v
                        elif k == "flags" and not flags_sample:
                            flags_sample = v.split()[:12]
        except Exception:
            pass

    cpu_freq = psutil.cpu_freq()
    return {
        "source": "/proc/cpuinfo e psutil",
        "model_name": model_name,
        "vendor_id": vendor_id,
        "cache_size": cache_size,
        "physical_cores": cpu_cores,
        "logical_cpus": logical_cpus,
        "frequency_mhz": {
            "current": round(cpu_freq.current, 2) if cpu_freq else None,
            "min": round(cpu_freq.min, 2) if cpu_freq and cpu_freq.min else None,
            "max": round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None
        },
        "flags_sample": flags_sample
    }


def read_os_distribution_info() -> Dict[str, Any]:
    """Lê informações da distribuição Linux a partir de /etc/os-release e platform."""
    distro_info: Dict[str, Any] = {
        "system": platform.system(),
        "kernel_release": platform.release(),
        "architecture": platform.machine(),
        "platform_details": platform.platform()
    }

    os_release = Path("/etc/os-release")
    if os_release.exists():
        try:
            with open(os_release, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        distro_info[k.lower()] = v.strip('"')
            distro_info["source"] = "/etc/os-release"
        except Exception as e:
            distro_info["error_reading_os_release"] = str(e)
    else:
        distro_info["source"] = "platform"

    return distro_info


def read_storage_and_filesystems() -> Dict[str, Any]:
    """
    Coleta informações dos sistemas de arquivos montados, tamanho dos arquivos do projeto
    e contadores de I/O de disco.
    """
    partitions_info: List[Dict[str, Any]] = []
    try:
        for part in psutil.disk_partitions(all=False):
            # Filtra partições físicas relevantes
            if part.fstype in ("ext4", "xfs", "btrfs", "vfat", "ntfs", "tmpfs"):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    partitions_info.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "opts": part.opts,
                        "total_bytes": usage.total,
                        "total_gb": round(usage.total / (1024 ** 3), 2),
                        "used_bytes": usage.used,
                        "used_gb": round(usage.used / (1024 ** 3), 2),
                        "free_bytes": usage.free,
                        "free_gb": round(usage.free / (1024 ** 3), 2),
                        "percent_used": usage.percent
                    })
                except PermissionError:
                    continue
    except Exception:
        pass

    # Tamanho real dos arquivos de dados da aplicação
    sample_bin = DATA_DIR / "storage_benchmark_sample.bin"
    app_files = [
        {"name": "SQLite Database", "path": str(DATABASE_PATH), "file": DATABASE_PATH},
        {"name": "Vector Matrix (.npy)", "path": str(VECTORS_NPY_PATH), "file": VECTORS_NPY_PATH},
        {"name": "Vector Mapping (.json)", "path": str(VECTORS_MAP_PATH), "file": VECTORS_MAP_PATH},
        {"name": "Storage Benchmark Sample", "path": str(sample_bin), "file": sample_bin}
    ]

    files_metrics = []
    for item in app_files:
        fpath = item["file"]
        if fpath.exists():
            stat = fpath.stat()
            files_metrics.append({
                "name": item["name"],
                "path": item["path"],
                "exists": True,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "last_modified_unix": round(stat.st_mtime, 2)
            })
        else:
            files_metrics.append({
                "name": item["name"],
                "path": item["path"],
                "exists": False,
                "size_bytes": 0,
                "size_mb": 0.0,
                "last_modified_unix": None
            })

    # Contadores de I/O globais de disco
    disk_io = psutil.disk_io_counters(perdisk=False)
    io_metrics = {
        "read_count": disk_io.read_count if disk_io else None,
        "write_count": disk_io.write_count if disk_io else None,
        "read_bytes": disk_io.read_bytes if disk_io else None,
        "read_mb": round(disk_io.read_bytes / (1024 * 1024), 2) if disk_io else None,
        "write_bytes": disk_io.write_bytes if disk_io else None,
        "write_mb": round(disk_io.write_bytes / (1024 * 1024), 2) if disk_io else None,
        "read_time_ms": disk_io.read_time if disk_io else None,
        "write_time_ms": disk_io.write_time if disk_io else None
    }

    return {
        "source": "psutil.disk_partitions e psutil.disk_io_counters",
        "partitions": partitions_info,
        "application_data_files": files_metrics,
        "physical_disk_io_counters": io_metrics,
        "io_distinction_notes": {
            "app_requested_vs_physical": (
                "Bytes solicitados pela aplicação (ex: fatias de leitura em C1 e C2) "
                "são contabilizados em rchar (/proc/[pid]/io). Já read_bytes em /proc/[pid]/io "
                "e physical_disk_io_counters registram apenas os dados que realmente demandaram I/O físico no disco. "
                "Se o arquivo estiver no Page Cache, read_bytes permanecerá zerado ou inalterado."
            )
        }
    }


def read_process_detailed_metrics(pid: Optional[int] = None) -> Dict[str, Any]:
    """
    Coleta métricas detalhadas do processo corrente (ou PID especificado) e filhos.
    """
    target_pid = pid or os.getpid()
    try:
        p = psutil.Process(target_pid)
    except psutil.NoSuchProcess:
        return {
            "available": False,
            "pid": target_pid,
            "error": f"Processo com PID {target_pid} não encontrado."
        }

    mem_info = p.memory_info()
    cpu_times = p.cpu_times()
    rusage = resource.getrusage(resource.RUSAGE_SELF)

    # Contadores de I/O do processo em Linux (/proc/[pid]/io)
    proc_io = {}
    io_file = Path(f"/proc/{target_pid}/io")
    if io_file.exists():
        try:
            with open(io_file, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.strip().split(":", 1)
                        proc_io[k.strip()] = int(v.strip())
        except Exception:
            pass

    # Filhos do processo
    children_info = []
    try:
        for child in p.children(recursive=True):
            try:
                cmem = child.memory_info()
                children_info.append({
                    "pid": child.pid,
                    "name": child.name(),
                    "status": child.status(),
                    "rss_mb": round(cmem.rss / (1024 * 1024), 2),
                    "cpu_percent": child.cpu_percent(interval=None)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    return {
        "source": f"/proc/{target_pid} e resource.getrusage",
        "process_identification": {
            "pid": p.pid,
            "ppid": p.ppid(),
            "name": p.name(),
            "status": p.status(),
            "create_time_unix": round(p.create_time(), 2)
        },
        "memory": {
            "rss_bytes": mem_info.rss,
            "rss_mb": round(mem_info.rss / (1024 * 1024), 2),
            "vsz_bytes": mem_info.vms,
            "vsz_mb": round(mem_info.vms / (1024 * 1024), 2),
            "memory_percent": round(p.memory_percent(), 2),
            "distinction": "RSS é a memória física real alocada na RAM; VSZ/VMS é o espaço de endereçamento virtual total alocado."
        },
        "cpu": {
            "cpu_percent": p.cpu_percent(interval=None),
            "user_seconds": round(cpu_times.user, 3),
            "system_seconds": round(cpu_times.system, 3),
            "total_seconds": round(cpu_times.user + cpu_times.system, 3)
        },
        "concurrency": {
            "num_threads": p.num_threads(),
            "children_count": len(children_info),
            "children": children_info
        },
        "page_faults": {
            "minor_faults": rusage.ru_minflt,
            "major_faults": rusage.ru_majflt,
            "explanation": (
                "Minor faults: páginas resolvidas na RAM/Page Cache sem I/O físico de disco. "
                "Major faults: páginas que exigiram leitura física de disco ou swap."
            )
        },
        "io_counters": {
            "rchar": proc_io.get("rchar"),
            "wchar": proc_io.get("wchar"),
            "syscr": proc_io.get("syscr"),
            "syscw": proc_io.get("syscw"),
            "read_bytes": proc_io.get("read_bytes"),
            "write_bytes": proc_io.get("write_bytes"),
            "cancelled_write_bytes": proc_io.get("cancelled_write_bytes"),
            "distinction": (
                "rchar representa bytes solicitados por chamadas read() no espaço de usuário. "
                "read_bytes representa bytes que efetivamente exigiram transferência do subsistema de armazenamento."
            )
        }
    }


def read_gpu_detailed_metrics() -> Dict[str, Any]:
    """Obtém telemetria real da GPU via nvidia-smi."""
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,driver_version",
                "--format=csv,noheader,nounits"
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0
        ).strip()
        if output:
            parts = [p.strip() for p in output.split(",")]
            return {
                "available": True,
                "source": "nvidia-smi",
                "model": parts[0] if len(parts) > 0 else "Unknown",
                "memory_total_mb": float(parts[1]) if len(parts) > 1 else None,
                "memory_used_mb": float(parts[2]) if len(parts) > 2 else None,
                "memory_free_mb": float(parts[3]) if len(parts) > 3 else None,
                "gpu_utilization_percent": float(parts[4]) if len(parts) > 4 else None,
                "temperature_celsius": float(parts[5]) if len(parts) > 5 else None,
                "driver_version": parts[6] if len(parts) > 6 else "Unknown"
            }
    except Exception:
        pass

    return {
        "available": False,
        "source": "nvidia-smi",
        "model": None,
        "memory_total_mb": None,
        "driver_version": None,
        "note": "GPU NVIDIA ou nvidia-smi indisponível no ambiente"
    }
