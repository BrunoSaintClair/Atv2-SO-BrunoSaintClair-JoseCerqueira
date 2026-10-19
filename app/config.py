"""Configurações centrais do GenResearch-Servidor."""

import os
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CORPUS_DIR = DATA_DIR / "corpus"
RESULTS_DIR = BASE_DIR / "results"
CSV_RESULTS_DIR = RESULTS_DIR / "csv"
JSON_RESULTS_DIR = RESULTS_DIR / "json"
PLOTS_RESULTS_DIR = RESULTS_DIR / "plots"

# Banco de dados SQLite e arquivos de vetores
DATABASE_PATH = DATA_DIR / "genresearch.db"
VECTORS_NPY_PATH = DATA_DIR / "vectors.npy"
VECTORS_MAP_PATH = DATA_DIR / "vectors_map.json"

# Modelos locais (Ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_0")
OLLAMA_FALLBACK_GEN_MODEL = os.getenv("OLLAMA_FALLBACK_GEN_MODEL", "LFM2.5-2.6B")

# Limites e Parâmetros Operacionais do Pipeline RAG
MAX_DOCUMENT_SIZE_BYTES = int(os.getenv("MAX_DOCUMENT_SIZE_BYTES", str(5 * 1024 * 1024)))  # 5 MB
DEFAULT_CHUNK_SIZE = int(os.getenv("DEFAULT_CHUNK_SIZE", "500"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "50"))
MAX_CHUNKS_PER_DOC = int(os.getenv("MAX_CHUNKS_PER_DOC", "2000"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "3"))
MAX_TOP_K = int(os.getenv("MAX_TOP_K", "20"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))
OLLAMA_GEN_TIMEOUT = float(os.getenv("OLLAMA_GEN_TIMEOUT", "60.0"))
OLLAMA_EMBED_TIMEOUT = float(os.getenv("OLLAMA_EMBED_TIMEOUT", "30.0"))

# Configurações de API
API_TITLE = "GenResearch-Servidor"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "API para estudo experimental de sistemas operacionais (memória, armazenamento, "
    "concorrência, cache e filas) em um pipeline de IA Generativa e RAG."
)
DEFAULT_PORT = int(os.getenv("PORT", "8001"))

# Garantir que diretórios existam
for directory in (DATA_DIR, CORPUS_DIR, RESULTS_DIR, CSV_RESULTS_DIR, JSON_RESULTS_DIR, PLOTS_RESULTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
