"""Rotas para catálogo de experimentos, execuções de C1–C6 e D, e download de artefatos."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import CSV_RESULTS_DIR, JSON_RESULTS_DIR, PLOTS_RESULTS_DIR
from app.experiments.exp_cache import run_cache_experiment
from app.experiments.exp_concurrency import run_concurrency_experiment
from app.experiments.exp_fault import run_fault_experiment
from app.experiments.exp_memory import run_memory_experiment
from app.experiments.exp_race_condition import run_race_condition_experiment
from app.experiments.exp_storage import run_storage_experiment
from app.experiments.registry import get_experiments_catalog
from app.services.metrics import record_request
from app.services.storage import get_experiment_runs

router = APIRouter(prefix="/experiments", tags=["Experimentos"])


# =====================================================================
# Modelos Pydantic de Entrada para os Experimentos
# =====================================================================

class RaceConditionRequest(BaseModel):
    num_threads: int = Field(4, ge=2, le=32, description="Threads concorrentes competindo pelo contador")
    increments_per_thread: int = Field(1000, ge=10, le=50000, description="Incrementos por thread")
    mode: str = Field("both", pattern="^(unsynchronized|synchronized|both)$", description="'unsynchronized', 'synchronized' ou 'both'")
    repeat: int = Field(3, ge=1, le=10, description="Repetições por modo")
    inject_interleaving: bool = Field(True, description="Habilita chaveamento de contexto forçado (time.sleep(0))")


class StorageExperimentRequest(BaseModel):
    file_size_mb: int = Field(10, ge=1, le=50, description="Tamanho do arquivo binário de teste em MB")
    chunk_size_kb: int = Field(64, ge=4, le=1024, description="Granularidade do bloco de leitura em KiB")
    repeat: int = Field(3, ge=1, le=10, description="Repetições estatísticas")


class ConcurrencyExperimentRequest(BaseModel):
    workers_list: List[int] = Field([1, 2, 4], description="Configurações de workers concorrentes para comparar")
    tasks_per_trial: int = Field(20, ge=4, le=100, description="Quantidade de tarefas por rodada")
    queue_capacity: int = Field(10, ge=2, le=100, description="Capacidade máxima da fila circular")
    work_ms: float = Field(15.0, ge=1.0, le=200.0, description="Duração computacional por tarefa em ms")
    repeat: int = Field(3, ge=1, le=10, description="Número de repetições por configuração")


class CacheExperimentRequest(BaseModel):
    cache_capacity: int = Field(10, ge=2, le=50, description="Capacidade máxima do cache LRU")
    distinct_queries_count: int = Field(10, ge=2, le=50, description="Quantidade de consultas distintas (Cache Frio)")
    repeat_queries_count: int = Field(10, ge=2, le=100, description="Quantidade de consultas repetidas (Cache Aquecido)")
    work_ms: float = Field(15.0, ge=1.0, le=100.0, description="Custo simulado de busca/geração em ms")
    repeat: int = Field(3, ge=1, le=10, description="Repetições estatísticas")


class MemoryExperimentRequest(BaseModel):
    allocation_steps_mb: List[int] = Field([100, 250, 500], description="Degraus de alocação de memória em MB")
    hold_duration_sec: float = Field(0.5, ge=0.1, le=5.0, description="Tempo de retenção antes de liberar")
    repeat: int = Field(3, ge=1, le=10, description="Repetições por patamar")


class FaultExperimentRequest(BaseModel):
    faulty_tasks_count: int = Field(10, ge=2, le=50, description="Tarefas com erro proposital introduzidas")
    healthy_tasks_count: int = Field(10, ge=2, le=50, description="Tarefas saudáveis para teste de continuidade")
    max_retries: int = Field(2, ge=1, le=5, description="Política de retentativas antes de falha permanente")
    repeat: int = Field(3, ge=1, le=10, description="Repetições estatísticas")


# =====================================================================
# Rotas do Catálogo e Experimentos C1–C6 e D
# =====================================================================

@router.get("", summary="Lista os experimentos disponíveis e seus estados de implementação")
def list_experiments() -> List[Dict[str, Any]]:
    """Lista todos os experimentos previstos (C1 a C6 e D) com status e variáveis de controle."""
    record_request()
    return get_experiments_catalog()


@router.post("/race-condition", summary="Executa o Experimento D: Condição de Corrida vs Sincronização")
def run_race_condition(payload: RaceConditionRequest) -> Dict[str, Any]:
    """Demonstra de forma controlada a perda de atualizações e a correção com Lock."""
    record_request()
    return run_race_condition_experiment(
        num_threads=payload.num_threads,
        increments_per_thread=payload.increments_per_thread,
        mode=payload.mode,
        repeat=payload.repeat,
        inject_interleaving=payload.inject_interleaving
    )


@router.post("/c1-read", summary="Executa o Experimento C1: Leitura Convencional de Arquivos (open/read)")
def run_c1_read(payload: StorageExperimentRequest) -> Dict[str, Any]:
    """Mede tempo, taxa de transferência e page faults da leitura convencional."""
    record_request()
    return run_storage_experiment(
        mode="conventional",
        file_size_mb=payload.file_size_mb,
        chunk_size_kb=payload.chunk_size_kb,
        repeat=payload.repeat
    )


@router.post("/c2-mmap", summary="Executa o Experimento C2: Leitura via Mapeamento de Memória (mmap)")
def run_c2_mmap(payload: StorageExperimentRequest) -> Dict[str, Any]:
    """Mede tempo, taxa de transferência e page faults da leitura por memória virtual mapeada."""
    record_request()
    return run_storage_experiment(
        mode="mmap",
        file_size_mb=payload.file_size_mb,
        chunk_size_kb=payload.chunk_size_kb,
        repeat=payload.repeat
    )


@router.post("/c1-c2-compare", summary="Executa Comparação Direta C1 vs C2 (read vs mmap)")
def run_c1_c2_compare(payload: StorageExperimentRequest) -> Dict[str, Any]:
    """Executa C1 e C2 sequencialmente sobre o mesmo corpus binário e calcula speedup/diferença."""
    record_request()
    return run_storage_experiment(
        mode="both",
        file_size_mb=payload.file_size_mb,
        chunk_size_kb=payload.chunk_size_kb,
        repeat=payload.repeat
    )


@router.post("/c3-concurrency", summary="Executa o Experimento C3: Escalabilidade da Fila (1, 2 e 4 Workers)")
def run_c3_concurrency(payload: ConcurrencyExperimentRequest) -> Dict[str, Any]:
    """Avalia vazão, latência média e tempo de espera na fila variando a concorrência de consumidores."""
    record_request()
    return run_concurrency_experiment(
        workers_list=payload.workers_list,
        tasks_per_trial=payload.tasks_per_trial,
        queue_capacity=payload.queue_capacity,
        work_ms=payload.work_ms,
        repeat=payload.repeat
    )


@router.post("/c4-cache", summary="Executa o Experimento C4: Eficiência do Cache LRU Compartilhado")
def run_c4_cache(payload: CacheExperimentRequest) -> Dict[str, Any]:
    """Avalia tempo de resposta, hit rate e evicções sob cenários: Sem Cache, Frio, Aquecido e Transbordo."""
    record_request()
    return run_cache_experiment(
        cache_capacity=payload.cache_capacity,
        distinct_queries_count=payload.distinct_queries_count,
        repeat_queries_count=payload.repeat_queries_count,
        work_ms=payload.work_ms,
        repeat=payload.repeat
    )


@router.post("/c5-memory-pressure", summary="Executa o Experimento C5: Impacto de Memória sob Carga")
def run_c5_memory_pressure(payload: MemoryExperimentRequest) -> Dict[str, Any]:
    """Avalia RSS, VSZ, Swap e Minor Page Faults sob alocações graduais e liberação explícita com GC."""
    record_request()
    return run_memory_experiment(
        allocation_steps_mb=payload.allocation_steps_mb,
        hold_duration_sec=payload.hold_duration_sec,
        repeat=payload.repeat
    )


@router.post("/c6-fault-tolerance", summary="Executa o Experimento C6: Tolerância a Falhas e Recuperação")
def run_c6_fault_tolerance(payload: FaultExperimentRequest) -> Dict[str, Any]:
    """Injeta falhas intencionais, testa política de retentativa/descarte e saturação de fila."""
    record_request()
    return run_fault_experiment(
        faulty_tasks_count=payload.faulty_tasks_count,
        healthy_tasks_count=payload.healthy_tasks_count,
        max_retries=payload.max_retries,
        repeat=payload.repeat
    )


# =====================================================================
# Consulta de Histórico e Download de Artefatos Gerados
# =====================================================================

@router.get("/{experiment_code}/results", summary="Consulta histórico persistido no SQLite de um experimento")
def get_experiment_history(
    experiment_code: str,
    limit: int = Query(50, ge=1, le=200)
) -> List[Dict[str, Any]]:
    """Retorna as execuções salvas no banco de dados para o código informado (ex: EXP_C3_CONCURRENCY)."""
    record_request()
    code = experiment_code.upper()
    if not code.startswith("EXP_"):
        code = f"EXP_{code}"
    return get_experiment_runs(experiment_code=code, limit=limit)


@router.get("/{experiment_code}/plot", summary="Visualiza o gráfico PNG gerado pelo experimento")
def get_experiment_plot(experiment_code: str):
    """Retorna o gráfico PNG renderizado via Matplotlib para o experimento solicitado."""
    record_request()
    code = experiment_code.lower().replace("-", "_")
    candidates = [
        PLOTS_RESULTS_DIR / f"{code}.png",
        PLOTS_RESULTS_DIR / f"{code}_storage_comparison.png",
        PLOTS_RESULTS_DIR / f"{code}_workers.png",
        PLOTS_RESULTS_DIR / f"{code}_hit_rate.png",
        PLOTS_RESULTS_DIR / f"{code}_pressure.png",
        PLOTS_RESULTS_DIR / f"{code}_tolerance.png",
        PLOTS_RESULTS_DIR / f"{code}_comparison.png"
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(path, media_type="image/png", filename=path.name)

    # Busca genérica pelo prefixo no diretório de gráficos
    for file in PLOTS_RESULTS_DIR.glob(f"*{code}*.png"):
        return FileResponse(file, media_type="image/png", filename=file.name)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Nenhum gráfico encontrado para '{experiment_code}'. Execute o experimento primeiro."
    )


@router.get("/{experiment_code}/csv", summary="Baixa os dados tabulares em CSV gerados pelo experimento")
def get_experiment_csv(experiment_code: str):
    """Retorna o arquivo CSV com todos os trials e repetições brutas do experimento."""
    record_request()
    code = experiment_code.lower().replace("-", "_")
    csv_file = CSV_RESULTS_DIR / f"{code}.csv"
    if not csv_file.exists():
        # Tenta buscar por substring
        matches = list(CSV_RESULTS_DIR.glob(f"*{code}*.csv"))
        if matches:
            csv_file = matches[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Arquivo CSV não encontrado para '{experiment_code}'. Execute o experimento primeiro."
            )

    return FileResponse(csv_file, media_type="text/csv", filename=csv_file.name)
