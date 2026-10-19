"""Serviço de geração de embeddings reais utilizando o modelo local nomic-embed-text via Ollama."""

import logging
from typing import List, Tuple
import httpx
import numpy as np

from app.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_EMBED_TIMEOUT

logger = logging.getLogger("genresearch.embeddings")


class EmbeddingModelUnavailableError(RuntimeError):
    """Exceção levantada quando o serviço local de embeddings ou o modelo não está disponível."""
    pass


def check_embedding_model_status() -> dict:
    """Verifica se o Ollama está operacional e se o modelo de embeddings está presente."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                model_found = any(OLLAMA_EMBED_MODEL in name for name in models)
                return {
                    "available": model_found,
                    "service_online": True,
                    "model_configured": OLLAMA_EMBED_MODEL,
                    "model_installed": model_found,
                    "instructions": None if model_found else f"Execute: ollama pull {OLLAMA_EMBED_MODEL}"
                }
    except Exception as exc:
        return {
            "available": False,
            "service_online": False,
            "model_configured": OLLAMA_EMBED_MODEL,
            "model_installed": False,
            "instructions": f"Certifique-se de que o Ollama está ativo em {OLLAMA_BASE_URL} (ex: ollama serve)."
        }

    return {
        "available": False,
        "service_online": True,
        "model_configured": OLLAMA_EMBED_MODEL,
        "model_installed": False,
        "instructions": f"Execute: ollama pull {OLLAMA_EMBED_MODEL}"
    }


def generate_embedding(text: str) -> Tuple[np.ndarray, bytes, int]:
    """
    Gera o embedding vetorial real para um texto utilizando o modelo local nomic-embed-text.
    
    Retorna uma tupla:
      - vetor numpy float32 normalizado L2
      - bytes do vetor serializado
      - dimensão do vetor (ex: 768)
      
    Levanta EmbeddingModelUnavailableError se o modelo local estiver inacessível.
    NUNCA gera vetores aleatórios ou substitutos artificiais.
    """
    if not text or not text.strip():
        raise ValueError("O texto para geração de embedding não pode ser vazio.")

    try:
        with httpx.Client(timeout=OLLAMA_EMBED_TIMEOUT) as client:
            response = client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={
                    "model": OLLAMA_EMBED_MODEL,
                    "prompt": text
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                raw_vec = data.get("embedding", [])
                if not raw_vec:
                    raise EmbeddingModelUnavailableError(
                        f"Ollama retornou vetor vazio para o modelo '{OLLAMA_EMBED_MODEL}'."
                    )
                
                vec = np.array(raw_vec, dtype=np.float32)
                # Normalização L2 para cálculo eficiente de similaridade de cosseno via produto escalar
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                
                return vec, vec.tobytes(), len(vec)
            
            elif response.status_code == 404:
                raise EmbeddingModelUnavailableError(
                    f"Modelo '{OLLAMA_EMBED_MODEL}' não encontrado no Ollama local. "
                    f"Instale os pesos executando: ollama pull {OLLAMA_EMBED_MODEL}"
                )
            else:
                raise EmbeddingModelUnavailableError(
                    f"Erro retornado pelo Ollama (HTTP {response.status_code}): {response.text}"
                )
                
    except httpx.RequestError as exc:
        raise EmbeddingModelUnavailableError(
            f"Não foi possível conectar ao serviço Ollama em {OLLAMA_BASE_URL}. "
            f"Verifique se o daemon está ativo (ollama serve). Detalhe: {str(exc)}"
        ) from exc
