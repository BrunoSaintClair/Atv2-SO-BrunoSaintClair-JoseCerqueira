"""Serviço de persistência local utilizando SQLite com modo WAL e armazenamento de vetores em arquivos NumPy."""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
import numpy as np

from app.config import DATABASE_PATH, VECTORS_MAP_PATH, VECTORS_NPY_PATH

# Locks para serialização de concorrência
_db_write_lock = threading.Lock()
_vector_file_lock = threading.Lock()


def get_db_path() -> Path:
    """Retorna o caminho do banco de dados configurado."""
    return DATABASE_PATH


@contextmanager
def get_db_connection(read_only: bool = False) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager para conexões seguras com o SQLite.
    
    Aplica WAL mode, timeout de contenção e integridade de chave estrangeira.
    Para operações de escrita, utiliza o lock do processo para evitar erros 'database is locked'.
    """
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    
    if read_only:
        try:
            yield conn
        finally:
            conn.close()
    else:
        with _db_write_lock:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()


def init_db() -> None:
    """
    Inicializa o banco de dados e cria as tabelas necessárias de maneira idempotente.
    """
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Tabela de documentos brutos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Tabela de fragmentos (chunks)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                embedding_blob BLOB,
                embedding_dim INTEGER,
                is_simulated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE
            );
        """)
        
        # Tabela para registro de logs de consultas (RAG)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT UNIQUE NOT NULL,
                question TEXT NOT NULL,
                retrieved_chunks_count INTEGER NOT NULL,
                answer TEXT,
                latency_ms REAL NOT NULL,
                cache_hit INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Tabela de execuções de experimentos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiment_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_code TEXT NOT NULL,
                run_id INTEGER NOT NULL,
                parameters_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                system_state_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks (doc_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_code ON experiment_runs (experiment_code);")


def save_document(
    doc_id: str,
    title: str,
    content: str,
    size_bytes: int,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Persiste os metadados e o conteúdo de um documento no SQLite."""
    meta_str = json.dumps(metadata or {})
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (doc_id, title, content, size_bytes, metadata_json)
            VALUES (?, ?, ?, ?, ?);
            """,
            (doc_id, title, content, size_bytes, meta_str)
        )


def save_chunks_and_vectors(
    doc_id: str,
    chunks: List[Dict[str, Any]],
    vectors: np.ndarray
) -> List[int]:
    """
    Persiste os chunks no SQLite e adiciona seus vetores à matriz NumPy persistida no disco.
    
    Retorna a lista dos IDs gerados para os chunks.
    """
    if len(chunks) != len(vectors):
        raise ValueError("Quantidade de chunks e vetores deve ser idêntica.")

    inserted_chunk_ids: List[int] = []
    dim = vectors.shape[1] if len(vectors) > 0 else 0

    # 1. Inserção dos chunks no SQLite
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for idx, chunk in enumerate(chunks):
            vec_bytes = vectors[idx].tobytes()
            cursor.execute(
                """
                INSERT INTO chunks (doc_id, chunk_index, content, token_count, embedding_blob, embedding_dim, is_simulated)
                VALUES (?, ?, ?, ?, ?, ?, 0);
                """,
                (doc_id, chunk["chunk_index"], chunk["content"], chunk["token_count"], vec_bytes, dim)
            )
            inserted_chunk_ids.append(cursor.lastrowid)

    # 2. Atualização atômica do arquivo de matriz vetorial NumPy e do arquivo de mapeamento
    with _vector_file_lock:
        if VECTORS_NPY_PATH.exists() and VECTORS_MAP_PATH.exists():
            existing_vectors = np.load(VECTORS_NPY_PATH)
            with open(VECTORS_MAP_PATH, "r", encoding="utf-8") as f:
                existing_map: List[int] = json.load(f)

            updated_vectors = np.vstack([existing_vectors, vectors])
            updated_map = existing_map + inserted_chunk_ids
        else:
            updated_vectors = vectors
            updated_map = inserted_chunk_ids

        # Salva a matriz atualizada
        np.save(VECTORS_NPY_PATH, updated_vectors)
        with open(VECTORS_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(updated_map, f)

    return inserted_chunk_ids


def load_vector_index(use_mmap: bool = False) -> Tuple[Optional[np.ndarray], List[int]]:
    """
    Carrega o índice de vetores normalizados e sua lista correspondente de chunk IDs.
    
    Se use_mmap for True, utiliza np.load com mmap_mode='r', demonstrando leitura mapeada.
    """
    with _vector_file_lock:
        if not VECTORS_NPY_PATH.exists() or not VECTORS_MAP_PATH.exists():
            return None, []

        mmap_mode = "r" if use_mmap else None
        vectors = np.load(VECTORS_NPY_PATH, mmap_mode=mmap_mode)
        with open(VECTORS_MAP_PATH, "r", encoding="utf-8") as f:
            chunk_ids: List[int] = json.load(f)

        return vectors, chunk_ids


def get_chunks_by_ids(chunk_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Recupera os registros de texto de chunks específicos pelo ID a partir do SQLite.
    Evita carregar o corpus inteiro na memória.
    """
    if not chunk_ids:
        return []

    placeholders = ",".join("?" for _ in chunk_ids)
    query = f"""
        SELECT id, doc_id, chunk_index, content, token_count
        FROM chunks
        WHERE id IN ({placeholders});
    """
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute(query, chunk_ids)
        rows = cursor.fetchall()
        
        # Mapeia em dicionário para preservar a ordem desejada da similaridade
        chunk_map = {row["id"]: dict(row) for row in rows}
        return [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]


def list_documents() -> List[Dict[str, Any]]:
    """Lista todos os documentos persistidos com estatísticas agregadas."""
    query = """
        SELECT 
            d.doc_id,
            d.title,
            d.size_bytes,
            d.metadata_json,
            d.created_at,
            COUNT(c.id) as chunks_count
        FROM documents d
        LEFT JOIN chunks c ON d.doc_id = c.doc_id
        GROUP BY d.id
        ORDER BY d.created_at DESC;
    """
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        
        result = []
        for r in rows:
            meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
            result.append({
                "doc_id": r["doc_id"],
                "title": r["title"],
                "size_bytes": r["size_bytes"],
                "metadata": meta,
                "chunks_count": r["chunks_count"],
                "created_at": r["created_at"]
            })
        return result


def get_document_details(doc_id: str) -> Optional[Dict[str, Any]]:
    """Recupera os detalhes completos de um documento e seus fragmentos."""
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE doc_id = ?;", (doc_id,))
        doc_row = cursor.fetchone()
        if not doc_row:
            return None

        cursor.execute(
            "SELECT id, chunk_index, content, token_count, embedding_dim FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC;",
            (doc_id,)
        )
        chunk_rows = cursor.fetchall()

        meta = json.loads(doc_row["metadata_json"]) if doc_row["metadata_json"] else {}
        return {
            "doc_id": doc_row["doc_id"],
            "title": doc_row["title"],
            "content": doc_row["content"],
            "size_bytes": doc_row["size_bytes"],
            "metadata": meta,
            "created_at": doc_row["created_at"],
            "chunks": [dict(c) for c in chunk_rows]
        }


def get_corpus_and_index_stats() -> Dict[str, Any]:
    """Retorna estatísticas detalhadas sobre o volume do corpus e do índice vetorial."""
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total_docs, COALESCE(SUM(size_bytes), 0) as total_size FROM documents;")
        doc_stats = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) as total_chunks FROM chunks;")
        chunk_stats = cursor.fetchone()

    db_size_bytes = DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
    vector_file_bytes = VECTORS_NPY_PATH.stat().st_size if VECTORS_NPY_PATH.exists() else 0

    vector_dim = 0
    total_indexed_vectors = 0
    with _vector_file_lock:
        if VECTORS_NPY_PATH.exists():
            try:
                # Lê cabeçalho do arquivo .npy sem carregar dados inteiros em memória
                with open(VECTORS_NPY_PATH, "rb") as f:
                    major, minor = np.lib.format.read_magic(f)
                    shape, _, _ = np.lib.format.read_array_header_1_0(f) if major == 1 else np.lib.format.read_array_header_2_0(f)
                    total_indexed_vectors = shape[0]
                    vector_dim = shape[1] if len(shape) > 1 else 0
            except Exception:
                pass

    return {
        "total_documents": doc_stats["total_docs"],
        "total_corpus_size_bytes": doc_stats["total_size"],
        "total_corpus_size_mb": round(doc_stats["total_size"] / (1024 * 1024), 3),
        "total_chunks": chunk_stats["total_chunks"],
        "total_indexed_vectors": total_indexed_vectors,
        "embedding_dimension": vector_dim,
        "vector_index_file_bytes": vector_file_bytes,
        "vector_index_file_kb": round(vector_file_bytes / 1024, 2),
        "database_file_bytes": db_size_bytes,
        "database_file_mb": round(db_size_bytes / (1024 * 1024), 2)
    }


def log_rag_query(
    request_id: str,
    question: str,
    retrieved_count: int,
    answer: str,
    latency_ms: float,
    cache_hit: bool = False
) -> None:
    """Registra uma consulta RAG e seus metadados de execução."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO query_logs (request_id, question, retrieved_chunks_count, answer, latency_ms, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (request_id, question, retrieved_count, answer, latency_ms, int(cache_hit))
        )
