"""Rotas para consulta do catálogo de experimentos e execução do Experimento D (Condição de Corrida)."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.experiments.exp_race_condition import run_race_condition_experiment
from app.experiments.registry import get_experiments_catalog
from app.services.metrics import record_request
from app.services.storage import get_experiment_runs

router = APIRouter(prefix="/experiments", tags=["Experimentos"])


class RaceConditionExperimentRequest(BaseModel):
    """Esquema de requisição para execução do experimento de condição de corrida."""
    num_threads: int = Field(
        4,
        ge=2,
        le=32,
        description="Número de threads concorrentes competindo pelo contador compartilhado"
    )
    increments_per_thread: int = Field(
        1000,
        ge=10,
        le=50000,
        description="Quantidade de operações de incremento executadas por cada thread"
    )
    mode: str = Field(
        "both",
        pattern="^(unsynchronized|synchronized|both)$",
        description="Modo de execução: 'unsynchronized' (sem lock), 'synchronized' (com lock) ou 'both' (ambos para comparação)"
    )
    repeat: int = Field(
        3,
        ge=1,
        le=10,
        description="Número de repetições por modo para significância estatística"
    )
    inject_interleaving: bool = Field(
        True,
        description="Habilita janela controlada de chaveamento de contexto (time.sleep(0)) entre leitura e escrita"
    )


@router.get("", summary="Lista os experimentos disponíveis e seus estados de implementação")
def list_experiments() -> List[Dict[str, Any]]:
    """
    Lista todos os experimentos previstos na atividade acadêmica (C1 a C6 e D),
    indicando variáveis investigadas e o estado atual de implementação de cada um.
    """
    record_request()
    return get_experiments_catalog()


@router.post(
    "/race-condition",
    summary="Executa o Experimento D: Condição de Corrida vs Sincronização com Lock",
    status_code=status.HTTP_200_OK
)
def run_race_condition(payload: RaceConditionExperimentRequest) -> Dict[str, Any]:
    """
    Demonstra de forma controlada e reproduzível a condição de corrida em um contador compartilhado:
    
    1. **Sem sincronização**: Múltiplas threads disputam a região crítica (Read-Modify-Write),
       gerando atualizações perdidas (lost updates) mensuráveis.
    2. **Com sincronização**: A mesma carga de trabalho é protegida por `threading.Lock`,
       garantindo que 100% dos incrementos sejam computados corretamente.
    
    Persiste automaticamente os resultados de cada repetição no SQLite.
    """
    record_request()
    try:
        results = run_race_condition_experiment(
            num_threads=payload.num_threads,
            increments_per_thread=payload.increments_per_thread,
            mode=payload.mode,
            repeat=payload.repeat,
            inject_interleaving=payload.inject_interleaving
        )
        return results
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro durante a execução do experimento de concorrência: {str(err)}"
        )


@router.get(
    "/race-condition/history",
    summary="Consulta o histórico persistido de execuções do Experimento D",
    status_code=status.HTTP_200_OK
)
def get_race_condition_history(limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    """Recupera os registros persistidos de execuções anteriores do Experimento D salvos no SQLite."""
    record_request()
    return get_experiment_runs(experiment_code="EXP_D_RACE_CONDITION", limit=limit)
