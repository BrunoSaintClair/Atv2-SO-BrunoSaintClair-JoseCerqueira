"""Serviço de fragmentação (chunking) de documentos."""

from typing import List, Dict, Any


def split_text_into_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    """
    Fragmenta o texto fornecido em pedaços com tamanho configurável e sobreposição.
    """
    chunks = []
    start = 0
    text_length = len(text)
    chunk_index = 0

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk_content = text[start:end]
        chunks.append({
            "chunk_index": chunk_index,
            "content": chunk_content,
            "token_count": len(chunk_content.split())
        })
        chunk_index += 1
        if end == text_length:
            break
        start += (chunk_size - overlap)

    return chunks
