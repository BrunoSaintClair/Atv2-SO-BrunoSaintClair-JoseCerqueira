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
| `POST` | `/query` | Executa consulta síncrona RAG com suporte ao Cache LRU compartilhado |
| `POST` | `/tasks/query` | Enfileira consulta RAG de forma assíncrona (operação de produtor) |
| `GET` | `/tasks/{task_id}` | Consulta estado, tempos de espera/execução e resultado de uma tarefa |
| `GET` | `/tasks` | Lista tarefas recentes registradas em memória |
| `GET` | `/tasks/metrics` | Métricas de concorrência, produtores, consumidores e ocupação da fila |
| `POST` | `/tasks/workers/scale` | Redimensiona dinamicamente a quantidade de workers ativos (1, 2, 4) |
| `POST` | `/tasks/capacity` | Altera dinamicamente a capacidade máxima da fila compartilhada |
| `GET` | `/cache/stats` | Estatísticas do Cache LRU (hits, misses, evictions, hit rate, tempo economizado) |
| `GET` | `/cache/keys` | Lista chaves armazenadas no cache ordenadas de LRU para MRU |
| `POST` | `/cache/capacity` | Redimensiona dinamicamente a capacidade do cache (demonstração de eviction) |
| `POST` | `/cache/clear` | Esvazia o cache e zera as métricas de acertos e falhas |
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

---

## 7. Fila Compartilhada e Concorrência

A aplicação implementa um padrão clássico de **Produtores e Consumidores** baseado em `queue.Queue` com capacidade limitada:

- **Produtores:** Múltiplas requisições HTTP submetem tarefas via `POST /tasks/query`. A resposta é imediata (`202 Accepted`), retornando o `task_id` sem bloquear o cliente.
- **Consumidores (Workers):** Threads em background retiram tarefas da fila com espera bloqueante (`Condition Variables`) e timeout, evitando espera ocupada (*busy-waiting*).
- **Controle de Saturação:** Se a fila atingir sua capacidade máxima (`maxsize`), novas tentativas de enfileiramento bloqueiam até o timeout configurado (`QUEUE_PUT_TIMEOUT = 3.0s`). Se não houver desocupação, a API rejeita com `HTTP 503 Service Unavailable`.
- **Escalonamento Dinâmico:** É possível redimensionar a quantidade de workers ativos (1, 2, 4) em tempo de execução via `POST /tasks/workers/scale`.

### Submeter uma Tarefa Assíncrona
```bash
curl -s -X POST http://localhost:8001/tasks/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Qual a funcao da MMU no Linux?", "top_k": 2, "use_cache": true}' | jq .
```

### Consultar o Estado e Resultado da Tarefa
```bash
curl -s http://localhost:8001/tasks/{task_id} | jq .
```

### Visualizar Métricas da Fila
```bash
curl -s http://localhost:8001/tasks/metrics | jq .
```

---

## 8. Cache Compartilhado LRU

O cache em memória (`SharedLRUCache`) armazena respostas de consultas frequentes:

- **Segurança Concorrente:** Todas as operações de leitura e escrita são protegidas por `threading.Lock`.
- **Chave Determinística:** Baseada no hash da pergunta normalizada e nos parâmetros que alteram a resposta (`top_k`, `max_context_chars`).
- **Política de Substituição:** Baseada em recência de acesso (`OrderedDict.move_to_end`). Ao atingir a capacidade, o item menos recentemente utilizado é desalocado (*eviction*).
- **Métricas:** Registra acertos (*hits*), falhas (*misses*), remoções (*evictions*), taxa de acerto (*hit rate*) e tempo de processamento economizado (*total_time_saved_ms*).

### Consultar Estatísticas do Cache
```bash
curl -s http://localhost:8001/cache/stats | jq .
```

### Inspecionar Ordem LRU das Chaves
```bash
curl -s http://localhost:8001/cache/keys | jq .
```

### Redimensionar Capacidade (Forçar Eviction)
```bash
curl -s -X POST http://localhost:8001/cache/capacity \
  -H "Content-Type: application/json" \
  -d '{"capacity": 5}' | jq .
```

---

## 9. Execução dos Scripts de Teste de Concorrência

Para validar de ponta a ponta o funcionamento concorrente e do cache, utilize os atalhos do `Makefile` ou execute os scripts diretamente:

```bash
# Executar todos os testes automatizados
make test

# Ou executar individualmente:
make test-concurrency   # Testa 2 produtores, 2 workers e o Cache LRU
make test-queue         # Testa saturação de fila cheia (HTTP 503) e escala de workers
```

Ou diretamente via Python:
```bash
./.venv/bin/python3 scripts/test_concurrency_and_cache.py
./.venv/bin/python3 scripts/test_queue_full_and_scaling.py
```
