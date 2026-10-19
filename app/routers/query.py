"""Rotas para consultas RAG, informações de índice e status dos modelos de IA local."""

import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import DEFAULT_TOP_K, MAX_CONTEXT_CHARS, MAX_TOP_K
from app.services.embeddings import (
    EmbeddingModelUnavailableError,
    check_embedding_model_status,
    generate_embedding
)
from app.services.generation import (
    GenerationInferenceError,
    GenerationModelUnavailableError,
    check_generation_model_status,
    generate_response
)
from app.services.cache import generate_cache_key, rag_cache
from app.services.metrics import record_request
from app.services.retrieval import retrieve_relevant_chunks
from app.services.storage import get_corpus_and_index_stats, log_rag_query

router = APIRouter(tags=["RAG & IA Local"])


class QueryRequest(BaseModel):
    """Esquema de requisição para consulta RAG."""
    question: str = Field(..., min_length=2, description="Pergunta a ser respondida com base no corpus")
    top_k: Optional[int] = Field(
        DEFAULT_TOP_K,
        ge=1,
        le=MAX_TOP_K,
        description="Número máximo de trechos relevantes a recuperar"
    )
    max_context_chars: Optional[int] = Field(
        MAX_CONTEXT_CHARS,
        ge=200,
        le=10000,
        description="Limite de caracteres do contexto repassado ao LLM"
    )
    use_cache: Optional[bool] = Field(
        True,
        description="Se habilitado, consulta e atualiza o Cache LRU compartilhado"
    )


@router.post("/query", summary="Executa uma consulta completa através do pipeline RAG")
def run_query(payload: QueryRequest) -> Dict[str, Any]:
    """
    Executa o pipeline RAG completo:
    1. Se use_cache=True, verifica se a resposta já está presente no Cache LRU compartilhado.
    2. Gera embedding da pergunta utilizando o modelo local nomic-embed-text.
    3. Recupera os trechos mais relevantes do corpus por similaridade de cosseno.
    4. Monta o contexto delimitado.
    5. Gera a resposta utilizando o modelo generativo local via Ollama.
    6. Atualiza o cache e registra tempos e metadados de execução.
    """
    record_request()
    request_id = str(uuid.uuid4())
    start_total = time.perf_counter_ns()
    
    top_k = payload.top_k or DEFAULT_TOP_K
    max_context = payload.max_context_chars or MAX_CONTEXT_CHARS
    use_cache = payload.use_cache if payload.use_cache is not None else True

    # 1. Verificação no Cache LRU Compartilhado
    cache_key = generate_cache_key(payload.question, top_k, max_context)
    if use_cache:
        cached_result = rag_cache.get(cache_key)
        if cached_result is not None:
            total_time_ms = (time.perf_counter_ns() - start_total) / 1_000_000.0
            log_rag_query(
                request_id=request_id,
                question=payload.question,
                retrieved_count=len(cached_result.get("retrieved_chunks", [])),
                answer=cached_result["answer"],
                latency_ms=total_time_ms,
                cache_hit=True
            )
            return {
                "request_id": request_id,
                "question": payload.question,
                "answer": cached_result["answer"],
                "model_used": cached_result["model_used"],
                "cache_hit": True,
                "retrieved_chunks_count": len(cached_result.get("retrieved_chunks", [])),
                "retrieved_chunks": cached_result.get("retrieved_chunks", []),
                "context_size_chars": cached_result.get("context_size_chars", 0),
                "timing": {
                    "cache_lookup_time_ms": round(total_time_ms, 2),
                    "total_time_ms": round(total_time_ms, 2)
                }
            }

    # 2. Geração de embedding da consulta
    start_query_embed = time.perf_counter_ns()
    try:
        query_vec, _, _ = generate_embedding(payload.question)
    except EmbeddingModelUnavailableError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha no modelo de embeddings: {str(err)}"
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )
    query_embed_time_ms = (time.perf_counter_ns() - start_query_embed) / 1_000_000.0

    # 3. Recuperação vetorial de trechos
    retrieved_chunks, retrieval_time_ms = retrieve_relevant_chunks(
        query_vector=query_vec,
        top_k=top_k
    )

    # 4. Geração de resposta com modelo local
    context_texts = [c["content"] for c in retrieved_chunks]
    try:
        generation_result = generate_response(
            question=payload.question,
            context_chunks=context_texts,
            max_context_chars=max_context
        )
    except GenerationModelUnavailableError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha no modelo generativo: {str(err)}"
        )
    except GenerationInferenceError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro de inferência no modelo generativo: {str(err)}"
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )

    total_time_ms = (time.perf_counter_ns() - start_total) / 1_000_000.0

    result_payload = {
        "answer": generation_result["answer"],
        "model_used": generation_result["model_used"],
        "retrieved_chunks": retrieved_chunks,
        "context_size_chars": generation_result["context_chars"]
    }

    # 5. Salva no Cache LRU
    if use_cache:
        rag_cache.put(cache_key, result_payload, latency_ms=total_time_ms)

    # 6. Registro persistente da consulta
    log_rag_query(
        request_id=request_id,
        question=payload.question,
        retrieved_count=len(retrieved_chunks),
        answer=generation_result["answer"],
        latency_ms=total_time_ms,
        cache_hit=False
    )

    return {
        "request_id": request_id,
        "question": payload.question,
        "answer": generation_result["answer"],
        "model_used": generation_result["model_used"],
        "cache_hit": False,
        "retrieved_chunks_count": len(retrieved_chunks),
        "retrieved_chunks": retrieved_chunks,
        "context_size_chars": generation_result["context_chars"],
        "timing": {
            "query_embedding_time_ms": round(query_embed_time_ms, 2),
            "retrieval_time_ms": round(retrieval_time_ms, 2),
            "generation_time_ms": round(generation_result["generation_time_ms"], 2),
            "total_time_ms": round(total_time_ms, 2)
        }
    }


@router.get("/corpus/info", summary="Visualiza informações agregadas do corpus e do índice vetorial")
def get_corpus_info() -> Dict[str, Any]:
    """Retorna volume de documentos, fragmentos, dimensões e tamanho dos arquivos de índice."""
    record_request()
    return get_corpus_and_index_stats()


@router.get("/ai/status", summary="Verifica a disponibilidade dos componentes de IA local")
def get_ai_status() -> Dict[str, Any]:
    """
    Avalia a saúde e a presença dos modelos locais exigidos:
    - nomic-embed-text (embeddings reais)
    - modelo generativo local configurado (Ollama)
    """
    record_request()
    embed_status = check_embedding_model_status()
    gen_status = check_generation_model_status()
    all_ready = embed_status["available"] and gen_status["available"]

    return {
        "status": "ready" if all_ready else "degraded",
        "embeddings": embed_status,
        "generation": gen_status
    }
