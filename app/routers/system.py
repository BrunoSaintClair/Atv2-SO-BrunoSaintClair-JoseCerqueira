"""Rotas de observação do ambiente operacional, memória Linux, processos, I/O e amostragem."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.linux_metrics import (
    read_os_distribution_info,
    read_proc_cpuinfo,
    read_proc_meminfo,
    read_process_detailed_metrics,
    read_storage_and_filesystems
)
from app.services.metrics import get_system_metrics, record_request
from app.services.sampler import ExperimentSamplerSession
from app.services.system_info import get_system_info

router = APIRouter(prefix="/system", tags=["Sistema"])

# Sessão manual de amostragem em background (opcional)
_manual_session: Optional[ExperimentSamplerSession] = None


class StartSamplingRequest(BaseModel):
    session_label: str = Field("MANUAL_SESSION", description="Identificador da sessão de amostragem")
    interval_sec: float = Field(0.2, ge=0.05, le=5.0, description="Intervalo entre coletas em segundos")


@router.get("/info", summary="Retorna informações observáveis do ambiente operacional")
def read_system_info() -> Dict[str, Any]:
    """
    Coleta dados reais do sistema operacional, processador, RAM, swap, GPU e runtime local.
    Campos não disponíveis no ambiente são explicitamente sinalizados sem dados fictícios.
    """
    record_request()
    return get_system_info()


@router.get("/metrics", summary="Retorna métricas de sistema (instantâneas vs acumuladas)")
def read_system_metrics() -> Dict[str, Any]:
    """
    Retorna métricas de processo e sistema divididas em:
    - Métricas Instantâneas (RSS, VSZ, CPU %, threads ativas)
    - Métricas Acumuladas (CPU time, uptime, page faults, contadores de I/O)
    - Limitações técnicas da observabilidade documentadas
    """
    record_request()
    return get_system_metrics()


@router.get("/memory", summary="Retorna detalhamento aprofundado da memória Linux (/proc/meminfo)")
def read_memory_details() -> Dict[str, Any]:
    """
    Retorna dados reais de /proc/meminfo:
    - MemFree vs MemAvailable
    - Buffers e Page Cache (Cached)
    - Memória Anônima (Active/Inactive anon, AnonPages)
    - Memória de Arquivos (Active/Inactive file)
    - Memória Compartilhada (Shmem) e Slabs de Kernel
    - Unidades explícitas e notas conceituais de Sistemas Operacionais
    """
    record_request()
    return read_proc_meminfo()


@router.get("/process", summary="Retorna métricas detalhadas do processo da aplicação e filhos")
def read_process_metrics(pid: Optional[int] = Query(None, description="PID opcional para consulta")) -> Dict[str, Any]:
    """
    Retorna métricas detalhadas de processo do Linux:
    - PID, PPID, status e tempo de criação
    - Memória: RSS real em RAM vs VSZ alocação virtual total
    - CPU: percentual e tempos de usuário/sistema
    - Concorrência: contagem de threads e processos filhos
    - Faltas de Página: minor faults (resolvidas em RAM) e major faults (I/O)
    - Contadores de I/O: rchar/wchar (solicitados) vs read_bytes/write_bytes (físicos)
    """
    record_request()
    return read_process_detailed_metrics(pid=pid)


@router.get("/storage", summary="Retorna informações dos sistemas de arquivos, arquivos do app e I/O de disco")
def read_storage_metrics() -> Dict[str, Any]:
    """
    Retorna métricas de armazenamento e I/O:
    - Sistemas de arquivos montados (espaço total, usado e disponível)
    - Arquivos de dados da aplicação (SQLite, matriz de vetores NumPy, amostra de benchmark)
    - Contadores de I/O de disco físicos globais
    - Diferenciação entre bytes solicitados no espaço de usuário e transferências físicas de disco
    """
    record_request()
    return read_storage_and_filesystems()


@router.post("/sampling/start", summary="Inicia uma sessão manual de amostragem em background")
def start_manual_sampling(payload: StartSamplingRequest) -> Dict[str, Any]:
    """Dispara uma thread de amostragem contínua de métricas em background com intervalo configurável."""
    global _manual_session
    record_request()
    if _manual_session is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Uma sessão de amostragem manual já está ativa. Encerre-a antes de iniciar outra."
        )

    _manual_session = ExperimentSamplerSession(
        experiment_code=payload.session_label.upper(),
        run_id=1,
        interval_sec=payload.interval_sec
    )
    _manual_session.start()
    return {
        "status": "started",
        "session_label": payload.session_label.upper(),
        "interval_sec": payload.interval_sec,
        "message": "Amostragem manual de telemetria iniciada em background."
    }


@router.post("/sampling/stop", summary="Encerra a sessão manual de amostragem e persiste as amostras")
def stop_manual_sampling() -> Dict[str, Any]:
    """Encerra a thread de amostragem em background e persiste todas as amostras coletadas no SQLite."""
    global _manual_session
    record_request()
    if _manual_session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhuma sessão de amostragem manual está em execução."
        )

    samples = _manual_session.stop()
    session_label = _manual_session.experiment_code
    _manual_session = None

    return {
        "status": "stopped",
        "session_label": session_label,
        "samples_collected_count": len(samples),
        "message": f"Sessão finalizada com sucesso. {len(samples)} amostras persistidas no SQLite."
    }


@router.get("/sampling/status", summary="Verifica se existe sessão manual de amostragem ativa")
def get_sampling_status() -> Dict[str, Any]:
    """Informa se há uma sessão manual de amostragem em execução no momento."""
    record_request()
    return {
        "is_active": _manual_session is not None,
        "session_label": _manual_session.experiment_code if _manual_session else None,
        "interval_sec": _manual_session.interval_sec if _manual_session else None,
        "samples_collected_so_far": len(_manual_session.samples) if _manual_session else 0
    }
