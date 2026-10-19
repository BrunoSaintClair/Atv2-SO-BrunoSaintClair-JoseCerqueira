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


@router.post("/query", summary="Executa uma consulta completa através do pipeline RAG")
def run_query(payload: QueryRequest) -> Dict[str, Any]:
    """
    Executa o pipeline RAG completo:
    1. Gera embedding da pergunta utilizando o modelo local nomic-embed-text.
    2. Recupera os trechos mais relevantes do corpus por similaridade de cosseno.
    3. Monta o contexto delimitado.
    4. Gera a resposta utilizando o modelo generativo local via Ollama.
    5. Registra tempos e metadados de execução.
    """
    record_request()
    request_id = str(uuid.uuid4())
    start_total = time.perf_counter_ns()

    # 1. Geração de embedding da consulta
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

    # 2. Recuperação vetorial de trechos
    retrieved_chunks, retrieval_time_ms = retrieve_relevant_chunks(
        query_vector=query_vec,
        top_k=payload.top_k or DEFAULT_TOP_K
    )

    # 3. Geração de resposta com modelo local
    context_texts = [c["content"] for c in retrieved_chunks]
    try:
        generation_result = generate_response(
            question=payload.question,
            context_chunks=context_texts,
            max_context_chars=payload.max_context_chars or MAX_CONTEXT_CHARS
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

    # 4. Registro persistente da consulta
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
