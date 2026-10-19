"""Serviço de recuperação vetorial por similaridade de cosseno utilizando matriz NumPy e SQLite."""

import time
from typing import Any, Dict, List, Tuple
import numpy as np

from app.config import DEFAULT_TOP_K, MAX_TOP_K
from app.services.storage import get_chunks_by_ids, load_vector_index


def retrieve_relevant_chunks(
    query_vector: np.ndarray,
    top_k: int = DEFAULT_TOP_K,
    use_mmap: bool = False
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Recupera os top-k fragmentos mais relevantes semanticamente.
    
    Etapas:
    1. Carrega a matriz de vetores (opcionalmente via mmap).
    2. Calcula similaridade de cosseno (produto escalar de vetores L2-normalizados).
    3. Seleciona os top-k índices mais similares.
    4. Consulta o SQLite apenas para os chunks vencedores, evitando carregar o corpus na RAM.
    
    Retorna uma tupla:
      - Lista de chunks com conteúdo, doc_id, chunk_index e score
      - Tempo de recuperação em milissegundos
    """
    start_time = time.perf_counter_ns()
    
    if top_k <= 0:
        top_k = DEFAULT_TOP_K
    top_k = min(top_k, MAX_TOP_K)

    vectors_matrix, chunk_ids = load_vector_index(use_mmap=use_mmap)
    if vectors_matrix is None or len(chunk_ids) == 0:
        elapsed_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0
        return [], round(elapsed_ms, 2)

    # Garante normalização L2 do vetor de consulta
    norm_q = np.linalg.norm(query_vector)
    if norm_q > 0:
        norm_query_vector = query_vector / norm_q
    else:
        norm_query_vector = query_vector

    # Cálculo vetorizado de similaridade de cosseno (matriz @ vetor)
    scores = np.dot(vectors_matrix, norm_query_vector)

    # Identificação dos top-k índices
    num_items = len(scores)
    actual_k = min(top_k, num_items)
    
    # Se k for pequeno relativo ao total, argpartition é O(N + K log K) em vez de O(N log N)
    if actual_k < num_items:
        partition_indices = np.argpartition(scores, -actual_k)[-actual_k:]
        sorted_top_indices = partition_indices[np.argsort(-scores[partition_indices])]
    else:
        sorted_top_indices = np.argsort(-scores)

    selected_chunk_ids = [chunk_ids[idx] for idx in sorted_top_indices]
    selected_scores = [float(scores[idx]) for idx in sorted_top_indices]

    # Busca no SQLite apenas os textos dos chunks selecionados
    chunks_records = get_chunks_by_ids(selected_chunk_ids)

    # Associa o score correspondente preservando a ordem
    score_by_id = dict(zip(selected_chunk_ids, selected_scores))
    results = []
    for chunk in chunks_records:
        cid = chunk["id"]
        results.append({
            "chunk_id": cid,
            "doc_id": chunk["doc_id"],
            "chunk_index": chunk["chunk_index"],
            "content": chunk["content"],
            "token_count": chunk["token_count"],
            "score": round(score_by_id.get(cid, 0.0), 4)
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    elapsed_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0
    return results, round(elapsed_ms, 2)
