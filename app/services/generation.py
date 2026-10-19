"""Serviço de geração de respostas utilizando modelo generativo local via Ollama."""

import logging
import time
from typing import Any, Dict, List
import httpx

from app.config import (
    MAX_CONTEXT_CHARS,
    OLLAMA_BASE_URL,
    OLLAMA_FALLBACK_GEN_MODEL,
    OLLAMA_GEN_MODEL,
    OLLAMA_GEN_TIMEOUT
)

logger = logging.getLogger("genresearch.generation")


class GenerationModelUnavailableError(RuntimeError):
    """Exceção levantada quando o modelo de geração ou o Ollama não está acessível."""
    pass


class GenerationInferenceError(RuntimeError):
    """Exceção levantada quando a inferência do modelo falha durante a execução."""
    pass


def resolve_active_generation_model() -> str:
    """Verifica e retorna o modelo de geração local disponível."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                installed = [m.get("name", "") for m in resp.json().get("models", [])]
                # Verifica modelo primário
                for name in installed:
                    if OLLAMA_GEN_MODEL in name:
                        return name
                # Verifica modelo fallback configurado
                for name in installed:
                    if OLLAMA_FALLBACK_GEN_MODEL in name:
                        return name
    except Exception:
        pass
    return OLLAMA_GEN_MODEL


def check_generation_model_status() -> dict:
    """Verifica a disponibilidade do modelo generativo local."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                installed = [m.get("name", "") for m in resp.json().get("models", [])]
                found_primary = any(OLLAMA_GEN_MODEL in name for name in installed)
                found_fallback = any(OLLAMA_FALLBACK_GEN_MODEL in name for name in installed)
                active = found_primary or found_fallback
                resolved = resolve_active_generation_model()
                
                return {
                    "available": active,
                    "service_online": True,
                    "model_configured": OLLAMA_GEN_MODEL,
                    "model_resolved": resolved if active else None,
                    "instructions": None if active else f"Execute: ollama run {OLLAMA_GEN_MODEL}"
                }
    except Exception as exc:
        return {
            "available": False,
            "service_online": False,
            "model_configured": OLLAMA_GEN_MODEL,
            "model_resolved": None,
            "instructions": f"Certifique-se de que o Ollama está ativo em {OLLAMA_BASE_URL} (ollama serve)."
        }

    return {
        "available": False,
        "service_online": True,
        "model_configured": OLLAMA_GEN_MODEL,
        "model_resolved": None,
        "instructions": f"Execute: ollama run {OLLAMA_GEN_MODEL}"
    }


def generate_response(
    question: str,
    context_chunks: List[str],
    max_context_chars: int = MAX_CONTEXT_CHARS
) -> Dict[str, Any]:
    """
    Executa a inferência real utilizando o modelo local configurado no Ollama.
    
    Limita o tamanho do contexto para evitar saturação de memória ou estresse desnecessário.
    NUNCA retorna respostas falsas ou substitutos simulados.
    """
    if not question or not question.strip():
        raise ValueError("A pergunta não pode ser vazia.")

    # Montagem do contexto limitado por tamanho de caracteres
    context_parts: List[str] = []
    current_length = 0
    
    for chunk in context_chunks:
        chunk_clean = chunk.strip()
        if not chunk_clean:
            continue
        if current_length + len(chunk_clean) > max_context_chars:
            # Corta ou interrompe a inclusão
            remaining = max_context_chars - current_length
            if remaining > 100:
                context_parts.append(chunk_clean[:remaining] + " [...]")
            break
        context_parts.append(chunk_clean)
        current_length += len(chunk_clean)

    assembled_context = "\n\n---\n\n".join(context_parts)
    
    prompt = (
        "Você é um assistente acadêmico técnico. Com base exclusivamente no contexto fornecido abaixo, "
        "responda de forma concisa e precisa à pergunta. Se o contexto não contiver as informações necessárias, "
        "declare explicitamente que as informações não estão presentes nos documentos recuperados.\n\n"
        f"--- CONTEXTO ---\n{assembled_context}\n\n"
        f"--- PERGUNTA ---\n{question.strip()}\n\n"
        f"--- RESPOSTA ---"
    )

    model_name = resolve_active_generation_model()
    start_time = time.perf_counter_ns()

    try:
        with httpx.Client(timeout=OLLAMA_GEN_TIMEOUT) as client:
            response = client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 512
                    }
                }
            )

            if response.status_code == 200:
                data = response.json()
                elapsed_ms = (time.perf_counter_ns() - start_time) / 1_000_000.0
                answer = data.get("response", "").strip()
                
                return {
                    "answer": answer,
                    "model_used": model_name,
                    "context_chars": len(assembled_context),
                    "generation_time_ms": round(elapsed_ms, 2)
                }
            elif response.status_code == 404:
                raise GenerationModelUnavailableError(
                    f"Modelo '{model_name}' não encontrado no Ollama. "
                    f"Baixe os pesos com: ollama pull {model_name}"
                )
            else:
                raise GenerationInferenceError(
                    f"Erro retornado pelo Ollama durante a geração (HTTP {response.status_code}): {response.text}"
                )

    except httpx.RequestError as exc:
        raise GenerationModelUnavailableError(
            f"Falha de conexão com o Ollama em {OLLAMA_BASE_URL}. "
            f"Verifique se o daemon está em execução (ollama serve). Detalhe: {str(exc)}"
        ) from exc
