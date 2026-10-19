"""Catálogo e registro de estado dos experimentos do GenResearch-Servidor."""

from typing import Any, Dict, List


def get_experiments_catalog() -> List[Dict[str, Any]]:
    """
    Retorna o catálogo completo dos experimentos definidos no plano de estudo,
    detalhando variáveis de controle, objetivos e status de implementação.
    """
    return [
        {
            "code": "C1",
            "name": "Leitura Convencional de Arquivos",
            "category": "Armazenamento e Memória Virtual",
            "status": "planejado",
            "description": (
                "Estabelece a linha de base de tempo, RSS e faltas de página utilizando "
                "leitura convencional com open() e read()."
            ),
            "variables": ["file_size_mb", "chunk_size_bytes", "cache_state"],
            "mandatory": True
        },
        {
            "code": "C2",
            "name": "Leitura por Memória Mapeada (mmap)",
            "category": "Armazenamento e Memória Virtual",
            "status": "planejado",
            "description": (
                "Avalia a leitura do corpus através de mapeamento de memória mmap.mmap(), "
                "comparando com C1 em latência, RSS e faltas de página sob page cache quente/frio."
            ),
            "variables": ["file_size_mb", "access_pattern", "cache_state"],
            "mandatory": True
        },
        {
            "code": "C3",
            "name": "Concorrência com Fila Compartilhada",
            "category": "Concorrência e Sincronização",
            "status": "planejado",
            "description": (
                "Avalia o comportamento de múltiplos produtores e consumidores concorrentes "
                "(1, 2 e 4 workers) sobre uma fila de requisições limitada."
            ),
            "variables": ["num_workers", "queue_max_size", "request_rate"],
            "mandatory": True
        },
        {
            "code": "C4",
            "name": "Cache Compartilhado e Substituição",
            "category": "Gerenciamento de Memória e Desempenho",
            "status": "planejado",
            "description": (
                "Mede a taxa de acerto (hit), taxa de erro (miss) e políticas de substituição "
                "em consultas repetidas e semanticamente variadas."
            ),
            "variables": ["cache_capacity", "repeat_ratio", "eviction_policy"],
            "mandatory": True
        },
        {
            "code": "C5",
            "name": "Pressão de Memória e Limites",
            "category": "Memória Principal e Virtual",
            "status": "planejado",
            "description": (
                "Aumenta controladamente o volume do corpus e lote para observar degradação, "
                "ocupação de RSS/VSZ e comportamento diante de esgotamento de memória."
            ),
            "variables": ["corpus_scale_factor", "batch_size"],
            "mandatory": False
        },
        {
            "code": "C6",
            "name": "Tratamento de Falhas Controladas",
            "category": "Robustez e Sistema Operacional",
            "status": "planejado",
            "description": (
                "Injeta falhas intencionais (arquivo inexistente, saturação de fila, timeout de LLM) "
                "e avalia a capacidade de recuperação e isolamento."
            ),
            "variables": ["fault_scenario", "timeout_threshold"],
            "mandatory": False
        },
        {
            "code": "D",
            "name": "Condição de Corrida e Sincronização Obrigatória",
            "category": "Sincronização",
            "status": "planejado",
            "description": (
                "Demonstra uma falha de sincronização (ex: atualização perdida no cache sem lock) "
                "e sua subsequente correção determinística utilizando primitivas de sincronização."
            ),
            "variables": ["concurrency_threads", "use_lock", "race_window_ms"],
            "mandatory": True
        }
    ]
