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
| `POST` | `/experiments/race-condition` | Executa o Experimento D (Condição de Corrida vs Lock) com métricas de perda |
| `POST` | `/experiments/c1-read` | Executa o Experimento C1 (Leitura Convencional com open/read) |
| `POST` | `/experiments/c2-mmap` | Executa o Experimento C2 (Leitura Mapeada com mmap) |
| `POST` | `/experiments/c1-c2-compare` | Executa Comparação Direta C1 vs C2 sequencialmente |
| `POST` | `/experiments/c3-concurrency` | Executa o Experimento C3 (Escalabilidade da Fila: 1, 2 e 4 Workers) |
| `POST` | `/experiments/c4-cache` | Executa o Experimento C4 (Eficiência do Cache LRU: Sem Cache, Frio, Aquecido) |
| `POST` | `/experiments/c5-memory-pressure` | Executa o Experimento C5 (Pressão de Memória: RSS, VSZ, Page Faults, GC) |
| `POST` | `/experiments/c6-fault-tolerance` | Executa o Experimento C6 (Tolerância a Falhas: Retry, Descarte, Saturação) |
| `GET` | `/experiments/{code}/results` | Consulta o histórico de execuções persistidas no SQLite (ex: EXP_C3_CONCURRENCY) |
| `GET` | `/experiments/{code}/plot` | Retorna o gráfico PNG gerado pelo experimento |
| `GET` | `/experiments/{code}/csv` | Baixa o arquivo CSV com dados brutos de cada repetição |


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
# Executar todos os testes automatizados (Experimento D + Fila + Cache)
make test

# Ou executar individualmente:
make test-race-condition # Executa o Experimento D (Condição de Corrida vs Sincronização)
make test-concurrency    # Testa 2 produtores, 2 workers e o Cache LRU
make test-queue          # Testa saturação de fila cheia (HTTP 503) e escala de workers
```

---

## 10. Experimento D — Demonstração de Condição de Corrida e Sincronização

O Experimento D demonstra o problema clássico de **Atualização Perdida (*Lost Update*)** em um recurso compartilhado (Read-Modify-Write) acessado por múltiplas threads simultâneas:

1. **Sem Proteção (`mode="unsynchronized"`):** As threads partem simultaneamente a partir de uma `threading.Barrier` e executam incrementos intercalados. Ocorre chaveamento de contexto no meio da leitura e escrita (`time.sleep(0)` cedendo a fatia de tempo), gerando **perdas médias de ~75% das atualizações**.
2. **Com Sincronização (`mode="synchronized"`):** A mesma carga é executada sob exclusão mútua garantida por `threading.Lock`. **0% de perdas** e 100% de consistência observada.
3. **Modo Comparativo (`mode="both"`):** Executa ambas as baterias com repetições configuráveis (padrão 3) e calcula a taxa de perda e a sobrecarga (*overhead*) de tempo do Lock.

### Como Executar pelo Swagger UI
1. Acesse: [http://localhost:8001/docs](http://localhost:8001/docs)
2. Localize a seção **Experimentos** e expanda `POST /experiments/race-condition`.
3. Clique em **Try it out** e utilize o payload padrão:
   ```json
   {
     "num_threads": 4,
     "increments_per_thread": 1000,
     "mode": "both",
     "repeat": 3,
     "inject_interleaving": true
   }
   ```
4. Clique em **Execute** e analise a resposta com o sumário comparativo.

### Como Executar via curl
```bash
curl -s -X POST http://localhost:8001/experiments/race-condition \
  -H "Content-Type: application/json" \
  -d '{
    "num_threads": 4,
    "increments_per_thread": 2000,
    "mode": "both",
    "repeat": 3,
    "inject_interleaving": true
  }' | jq .
```

### Consultar o Histórico Persistido no SQLite
```bash
curl -s http://localhost:8001/experiments/race-condition/history?limit=10 | jq .
```

---

## 11. Experimentos (C1 a C6)

Todos os experimentos foram implementados respeitando a regra de **dados reais gerados pelo próprio kernel Linux e processo do servidor**, sem geração de números artificiais ou fictícios.

### C1 — Leitura Convencional de Arquivos (`open()` e `read()`)
- **Conceito de SO:** Realiza cópia de dados do espaço de endereçamento do Kernel para o espaço de endereçamento do Usuário (*context-switch* e sobrecarga de cópia).
- **Endpoint:** `POST /experiments/c1-read`
- **Métricas:** Duração (ms), Vazão (MB/s), Minor Page Faults (`ru_minflt`), Major Page Faults (`ru_majflt`).

### C2 — Leitura Utilizando Mapeamento de Memória (`mmap`)
- **Conceito de SO:** Utiliza a chamada de sistema `mmap()` para mapear o arquivo diretamente na tabela de páginas do processo, eliminando a cópia redundante (*zero-copy*) e ativando paginação sob demanda (*lazy paging* via MMU).
- **Endpoint:** `POST /experiments/c2-mmap`
- **Comparação C1 vs C2:** `POST /experiments/c1-c2-compare`

### C3 — Concorrência na Fila Compartilhada (1, 2 e 4 Workers)
- **Conceito de SO:** Padrão clássico de Produtores e Consumidores concorrentes sobre buffer limitado (`queue.Queue`) sincronizado com variáveis de condição (`threading.Condition`).
- **Endpoint:** `POST /experiments/c3-concurrency`
- **Métricas:** Vazão (*throughput* em tarefas/s), Latência média (ms), Tempo de espera na fila (ms), Speedup escalando de 1 para 2 e 4 workers.

### C4 — Eficiência do Cache Compartilhado LRU
- **Conceito de SO:** Princípio da Localidade Temporal e Espacial com política determinística de substituição LRU (*Least Recently Used*). Proteção de região crítica via `threading.Lock`.
- **Endpoint:** `POST /experiments/c4-cache`
- **Cenários Avaliados:** Sem Cache, Cache Frio (Misses), Cache Aquecido (Hits 100%, redução drástica de latência) e Transbordo de Capacidade (Evicções LRU).

### C5 — Impacto de Memória sob Pressão Controlada
- **Conceito de SO:** Alocação de memória virtual (*lazy allocation* do Linux) versus consumo efetivo de memória física (RSS - *Resident Set Size*). O toque de página a cada 4 KiB gera faltas de página menores (*Minor Page Faults*) proporcionais ao tamanho alocado (ex: 25.600 faltas para 100 MB). Demonstração da liberação explícita de memória e Garbage Collection preventivo contra o *OOM Killer*.
- **Endpoint:** `POST /experiments/c5-memory-pressure`

### C6 — Tolerância a Falhas e Recuperação
- **Conceito de SO:** Isolamento de falhas, resiliência de pools de threads (*worker survivability*), política de retentativas (*retry*) versus descarte seguro (*permanent failure*), e controle de sobrecarga por contra-pressão (*backpressure*) em fila saturada com teste de continuidade de serviço.
- **Endpoint:** `POST /experiments/c6-fault-tolerance`

---

## 12. Consulta de Histórico e Download de Artefatos Gráficos e Tabulares

A API disponibiliza endpoints para recuperar os resultados persistidos no banco de dados SQLite (`genresearch.db`), bem como visualizar os gráficos renderizados pelo Matplotlib e baixar os arquivos brutos CSV:

| Rota | Tipo | Descrição |
|---|---|---|
| `GET /experiments/{code}/results` | JSON | Consulta histórico de execuções persistidas no SQLite (ex: `c1_c2`, `c3`, `c4`, `c5`, `c6`) |
| `GET /experiments/{code}/plot` | PNG | Baixa ou visualiza na interface o gráfico gerado pelo Matplotlib |
| `GET /experiments/{code}/csv` | CSV | Baixa a planilha tabular com todas as repetições e métricas do experimento |

### Exemplos via curl:
```bash
# Baixar o gráfico de escalabilidade C3
curl -s http://localhost:8001/experiments/c3/plot -o grafico_c3.png

# Baixar os dados brutos de memória C5 em CSV
curl -s http://localhost:8001/experiments/c5/csv -o dados_c5.csv
```

---

## 13. Limitações Conhecidas

1. **GIL (Global Interpreter Lock):** Como o runtime padrão do CPython utiliza GIL, tarefas puramente CPU-bound em threads não utilizam múltiplos núcleos simultaneamente. Contudo, as operações do nosso pipeline são primordialmente **I/O-bound** (chamadas de rede/HTTP locais ao daemon do Ollama e I/O de disco SQLite/NumPy), onde o GIL é prontamente liberado durante as operações de entrada e saída.
2. **Escala de Workers vs. Capacidade da GPU:** Aumentar indefinidamente o número de workers pode causar contenção de fila no próprio daemon do Ollama, que serializa ou enfileira inferências caso a VRAM da GPU seja saturada.
