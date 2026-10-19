# GenResearch-Servidor

Serviço experimental construído com **Python** e **FastAPI** para o estudo prático de conceitos de **Sistemas Operacionais** — incluindo gerenciamento de memória principal e virtual, armazenamento local, arquivos mapeados em memória (`mmap`), cache compartilhado, concorrência, filas e primitivas de sincronização — aplicados a uma carga de trabalho de IA Generativa e RAG (Retrieval-Augmented Generation).

---

## 1. Arquitetura do Pipeline RAG

O pipeline RAG opera através de uma integração desacoplada entre a API FastAPI, persistência relacional no SQLite, índices vetoriais em NumPy e inferência local acelerada por GPU via Ollama:

```
[Cliente HTTP] 
      │
      ▼
[API FastAPI] (Rotas modulares)
      │
      ├─► Ingestão:
      │     1. Fragmentação do texto em chunks (chunk_size, overlap).
      │     2. Geração de embeddings reais (nomic-embed-text via Ollama).
      │     3. Armazenamento de metadados e chunks no SQLite (genresearch.db).
      │     4. Persistência dos vetores normalizados L2 na matriz NumPy (vectors.npy).
      │
      └─► Consulta RAG:
            1. Geração de embedding da query com nomic-embed-text.
            2. Busca por similaridade de cosseno (produto escalar matrix @ query_vector).
            3. Resgate pontual dos top-k chunks no SQLite (evitando carregar corpus na RAM).
            4. Montagem de contexto com limite estrito de caracteres.
            5. Geração de resposta pelo modelo generativo local (LFM2.5-2.6B via Ollama).
            6. Registro persistente da consulta e métricas detalhadas de latência.
```

---

## 2. Requisitos e Modelos Locais

- **Sistema Operacional:** Linux (Ubuntu/Debian ou distribuição baseada em kernel Linux moderno).
- **Python:** 3.10+ (desenvolvido e testado em Python 3.12).
- **Ollama:** Runtime local instalado e em execução (`ollama serve`).

### Modelos Utilizados

1. **Embeddings:** `nomic-embed-text:latest`
   - *Justificativa:* Produz embeddings reais de 768 dimensões de alta qualidade para recuperação semântica, executando de forma ultraleve diretamente na GPU.
2. **Geração:** `hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` (ou alias `LFM2.5-2.6B`)
   - *Justificativa:* Modelo generativo local de 2.6 bilhões de parâmetros, compatível com os limites de VRAM da GPU dedicada (6 GB) e sem dependência de APIs externas na nuvem.

### Obtenção dos Pesos (Download Único Local)

Antes da execução dos experimentos, certifique-se de que os modelos estão presentes no Ollama:

```bash
# Iniciar o daemon caso não esteja ativo
ollama serve

# Baixar o modelo de embeddings (aprox. 274 MB)
ollama pull nomic-embed-text

# Baixar o modelo generativo LFM 2.5 (aprox. 1.6 GB)
ollama run hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_0
```

---

## 3. Instalação e Execução

### Passo 1: Configurar ambiente virtual e dependências

```bash
# Via Makefile
make setup

# Ou manualmente
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Passo 2: Iniciar a aplicação

```bash
# Via Makefile (porta padrão 8001)
make run

# Ou via Uvicorn diretamente
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
```

A API estará acessível em: `http://localhost:8001`  
Documentação Swagger interativa: [http://localhost:8001/docs](http://localhost:8001/docs)

---

## 4. Endpoints Disponíveis

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Identificação do serviço e links rápidos |
| `GET` | `/health` | Estado operacional e tempo de atividade da API |
| `GET` | `/system/info` | Informações observáveis reais do ambiente (Kernel, CPUs, RAM, Swap, GPU, Ollama) |
| `GET` | `/system/metrics` | Métricas divididas em instantâneas e acumuladas (RSS, VSZ, Page Faults, I/O) |
| `GET` | `/ai/status` | Verifica a conectividade e disponibilidade dos modelos de IA local |
| `POST` | `/documents` | Cadastra, fragmenta e ingere um documento gerando embeddings reais |
| `GET` | `/documents` | Lista documentos cadastrados e quantidade de chunks |
| `GET` | `/documents/{doc_id}` | Detalhes de um documento e de seus fragmentos persistidos |
| `GET` | `/corpus/info` | Estatísticas agregadas do corpus e do arquivo de índice vetorial |
| `POST` | `/query` | Executa consulta no pipeline RAG com recuperação vetorial e geração local |
| `GET` | `/experiments` | Lista catálogo dos experimentos C1 a C6 e D |

---

## 5. Exemplos Reais de Chamadas HTTP

### 1. Verificação de Saúde e IA Local
```bash
curl -s http://localhost:8001/ai/status | jq .
```

### 2. Ingestão de Documento
```bash
curl -s -X POST http://localhost:8001/documents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Gerenciamento de Memória Virtual e Paginação no Linux",
    "content": "O gerenciamento de memória virtual no Linux baseia-se no conceito de paginação sob demanda. Cada processo possui seu próprio espaço de endereçamento virtual isolado, dividido em páginas de tamanho fixo, tipicamente de 4 KiB na arquitetura x86-64. Minor page faults ocorrem quando a página está no Page Cache sem I/O de disco. Major page faults exigem leitura de disco ou partição de swap.",
    "chunk_size": 250,
    "chunk_overlap": 30,
    "metadata": {"disciplina": "Sistemas Operacionais", "topico": "memoria"}
  }' | jq .
```

*Resposta de exemplo:*
```json
{
  "doc_id": "176c8434-1381-4b05-b858-28d6482826b0",
  "title": "Gerenciamento de Memória Virtual e Paginação no Linux",
  "size_bytes": 435,
  "chunks_count": 2,
  "chunk_ids": [1, 2],
  "embedding_model": "nomic-embed-text",
  "embedding_dimension": 768,
  "timing": {
    "chunking_time_ms": 0.08,
    "embeddings_time_ms": 1240.5,
    "storage_time_ms": 12.1,
    "total_ingestion_time_ms": 1252.68
  }
}
```

### 3. Listagem e Detalhes de Documentos
```bash
# Listar todos os documentos
curl -s http://localhost:8001/documents | jq .

# Detalhes de um documento específico
curl -s http://localhost:8001/documents/{doc_id} | jq .
```

### 4. Informações do Corpus e Índice Vetorial
```bash
curl -s http://localhost:8001/corpus/info | jq .
```

### 5. Consulta pelo Pipeline RAG
```bash
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Qual a diferença entre minor page fault e major page fault no Linux?",
    "top_k": 3,
    "max_context_chars": 2000
  }' | jq .
```

*Resposta de exemplo:*
```json
{
  "request_id": "de81c1c5-2e8e-4864-8864-5f5cf6fed814",
  "question": "Qual a diferença entre minor page fault e major page fault no Linux?",
  "answer": "O Minor Page Fault ocorre quando a página já está residente na memória física (por exemplo, no Page Cache) e não exige acesso ao disco. Já o Major Page Fault exige leitura do armazenamento secundário ou partição de swap, gerando maior latência de I/O.",
  "model_used": "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_0",
  "retrieved_chunks_count": 3,
  "retrieved_chunks": [...],
  "context_size_chars": 1214,
  "timing": {
    "query_embedding_time_ms": 1520.12,
    "retrieval_time_ms": 2.04,
    "generation_time_ms": 13770.05,
    "total_time_ms": 15292.21
  }
}
```

---

## 6. Tratamento de Indisponibilidade e Limites

- **Modelo Inacessível (HTTP 503):** Se o daemon do Ollama estiver desligado ou o modelo requisitado não tiver os pesos baixados, a API retorna erro HTTP 503 com instruções de resolução:
  ```json
  {
    "detail": "Falha no modelo de embeddings: Modelo 'nomic-embed-text' não encontrado no Ollama local. Instale os pesos executando: ollama pull nomic-embed-text"
  }
  ```
- **Limites de Proteção:**
  - `MAX_DOCUMENT_SIZE_BYTES`: Rejeita documentos que excedam 5 MB (configurável).
  - `MAX_CHUNKS_PER_DOC`: Impede que um único documento gere mais de 2.000 chunks.
  - `MAX_TOP_K`: Limita o número de trechos recuperados a no máximo 20.
  - `MAX_CONTEXT_CHARS`: Trunca o contexto antes de enviar ao LLM, evitando estouro de janela e alocação abusiva de memória.
