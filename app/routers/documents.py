"""Rotas para cadastro, ingestão e listagem de documentos."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from app.services.embeddings import EmbeddingModelUnavailableError
from app.services.ingestion import (
    ChunksLimitExceededError,
    DocumentSizeLimitExceededError,
    ingest_document
)
from app.services.metrics import record_request
from app.services.storage import get_document_details, list_documents

router = APIRouter(prefix="/documents", tags=["Documentos"])


class DocumentCreateRequest(BaseModel):
    """Esquema de requisição para cadastro e ingestão de documento."""
    title: str = Field(..., min_length=1, max_length=255, description="Título descritivo do documento")
    content: str = Field(..., min_length=1, description="Texto completo do documento a ser ingerido")
    chunk_size: Optional[int] = Field(
        DEFAULT_CHUNK_SIZE,
        ge=50,
        le=5000,
        description="Tamanho de cada fragmento em caracteres"
    )
    chunk_overlap: Optional[int] = Field(
        DEFAULT_CHUNK_OVERLAP,
        ge=0,
        le=1000,
        description="Sobreposição entre fragmentos consecutivos"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Metadados arbitrários em formato JSON"
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Cadastra e ingere um documento no pipeline RAG")
def create_document(payload: DocumentCreateRequest) -> Dict[str, Any]:
    """
    Recebe um documento de texto, fragmenta em chunks, gera embeddings reais com o modelo local
    e persiste o documento e os vetores.
    """
    record_request()
    try:
        result = ingest_document(
            title=payload.title,
            content=payload.content,
            chunk_size=payload.chunk_size or DEFAULT_CHUNK_SIZE,
            chunk_overlap=payload.chunk_overlap or DEFAULT_CHUNK_OVERLAP,
            metadata=payload.metadata
        )
        return result
    except (DocumentSizeLimitExceededError, ChunksLimitExceededError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )
    except EmbeddingModelUnavailableError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err)
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno durante a ingestão do documento: {str(err)}"
        )


@router.get("", summary="Lista todos os documentos cadastrados")
def get_documents() -> List[Dict[str, Any]]:
    """Retorna a lista de documentos cadastrados com contagem de chunks e metadados."""
    record_request()
    return list_documents()


@router.get("/{doc_id}", summary="Consulta os detalhes de um documento e seus chunks")
def get_document(doc_id: str) -> Dict[str, Any]:
    """Retorna os dados completos do documento especificado e seus respectivos fragmentos."""
    record_request()
    doc = get_document_details(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento com doc_id '{doc_id}' não encontrado."
        )
    return doc
