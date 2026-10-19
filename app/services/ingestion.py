"""Serviço de ingestão de documentos com medição precisa de tempo por etapa."""

import time
import uuid
from typing import Any, Dict, List, Optional
import numpy as np

from app.config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    MAX_CHUNKS_PER_DOC,
    MAX_DOCUMENT_SIZE_BYTES,
    OLLAMA_EMBED_MODEL
)
from app.services.chunking import split_text_into_chunks
from app.services.embeddings import generate_embedding
from app.services.storage import save_chunks_and_vectors, save_document


class DocumentSizeLimitExceededError(ValueError):
    """Exceção levantada quando um documento excede o tamanho máximo configurado."""
    pass


class ChunksLimitExceededError(ValueError):
    """Exceção levantada quando a fragmentação excede o limite máximo de chunks por documento."""
    pass


def ingest_document(
    title: str,
    content: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executa a ingestão completa de um documento:
    1. Validação de limites de tamanho.
    2. Fragmentação em chunks (com medição de tempo).
    3. Geração de embeddings reais (com medição de tempo).
    4. Persistência dos metadados e chunks no SQLite e vetores no arquivo NumPy.
    
    Retorna estatísticas detalhadas com medições por fase.
    """
    start_total_time = time.perf_counter_ns()
    
    content_bytes = content.encode("utf-8")
    size_bytes = len(content_bytes)
    
    if size_bytes > MAX_DOCUMENT_SIZE_BYTES:
        raise DocumentSizeLimitExceededError(
            f"O documento excede o limite máximo de {MAX_DOCUMENT_SIZE_BYTES} bytes (recebido: {size_bytes} bytes)."
        )

    doc_id = str(uuid.uuid4())
    
    # 1. Fragmentação
    start_chunking = time.perf_counter_ns()
    chunks_data = split_text_into_chunks(content, chunk_size=chunk_size, overlap=chunk_overlap)
    chunking_time_ms = (time.perf_counter_ns() - start_chunking) / 1_000_000.0
    
    if len(chunks_data) > MAX_CHUNKS_PER_DOC:
        raise ChunksLimitExceededError(
            f"O documento gerou {len(chunks_data)} chunks, excedendo o limite de {MAX_CHUNKS_PER_DOC} chunks."
        )

    # 2. Geração de Embeddings Reais
    start_embeddings = time.perf_counter_ns()
    vectors_list: List[np.ndarray] = []
    
    for chunk in chunks_data:
        vec, _, _ = generate_embedding(chunk["content"])
        vectors_list.append(vec)
        
    embeddings_matrix = np.array(vectors_list, dtype=np.float32)
    embeddings_time_ms = (time.perf_counter_ns() - start_embeddings) / 1_000_000.0

    # 3. Persistência
    start_storage = time.perf_counter_ns()
    save_document(doc_id, title, content, size_bytes, metadata=metadata)
    chunk_ids = save_chunks_and_vectors(doc_id, chunks_data, embeddings_matrix)
    storage_time_ms = (time.perf_counter_ns() - start_storage) / 1_000_000.0

    total_time_ms = (time.perf_counter_ns() - start_total_time) / 1_000_000.0

    return {
        "doc_id": doc_id,
        "title": title,
        "size_bytes": size_bytes,
        "chunks_count": len(chunks_data),
        "chunk_ids": chunk_ids,
        "embedding_model": OLLAMA_EMBED_MODEL,
        "embedding_dimension": embeddings_matrix.shape[1] if len(embeddings_matrix) > 0 else 0,
        "timing": {
            "chunking_time_ms": round(chunking_time_ms, 2),
            "embeddings_time_ms": round(embeddings_time_ms, 2),
            "storage_time_ms": round(storage_time_ms, 2),
            "total_ingestion_time_ms": round(total_time_ms, 2)
        }
    }
