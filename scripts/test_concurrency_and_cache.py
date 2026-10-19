"""Script de validação dos mecanismos de concorrência e cache do GenResearch-Servidor."""

import concurrent.futures
import json
import time
import httpx

API_BASE = "http://localhost:8001"

def submit_task_from_producer(producer_id: str, question: str) -> dict:
    """Simula um produtor submetendo uma tarefa para a fila."""
    start = time.time()
    resp = httpx.post(
        f"{API_BASE}/tasks/query",
        json={"question": question, "top_k": 2, "use_cache": True},
        timeout=10.0
    )
    elapsed = round((time.time() - start) * 1000.0, 2)
    data = resp.json()
    data["producer_id"] = producer_id
    data["submission_latency_ms"] = elapsed
    return data

def main():
    print("=" * 60)
    print("1. TESTE DE CONCORRÊNCIA: 2 PRODUTORES SUBMETENDO TAREFAS")
    print("=" * 60)
    
    questions = [
        ("Produtor-1", "Qual a funcao da MMU no gerenciamento de memoria virtual?"),
        ("Produtor-2", "Como o mmap evita redundancia de copias de memoria?")
    ]
    
    # Executa os 2 produtores em paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(submit_task_from_producer, p_id, q)
            for p_id, q in questions
        ]
        submitted_tasks = [f.result() for f in concurrent.futures.as_completed(futures)]

    print("Tarefas enfileiradas pelos produtores:")
    for st in submitted_tasks:
        print(f"  [{st['producer_id']}] Task ID: {st['task_id']} | Status: {st['status']} | Latência HTTP: {st['submission_latency_ms']} ms")

    print("\nAguardando consumidores (workers) processarem as tarefas...")
    
    # Aguarda o processamento das tarefas pelos workers consumidores
    task_ids = [st["task_id"] for st in submitted_tasks]
    results = {}
    
    for tid in task_ids:
        for _ in range(60):
            r = httpx.get(f"{API_BASE}/tasks/{tid}", timeout=5.0).json()
            if r["status"] in ("completed", "failed"):
                results[tid] = r
                break
            time.sleep(1.0)

    print("\nResultado do processamento pelos consumidores:")
    for tid, res in results.items():
        print(f"  Task ID: {tid}")
        print(f"    Status: {res['status']}")
        print(f"    Consumidor (Worker): {res['worker_name']}")
        print(f"    Tempo de espera na fila: {res['timing']['wait_time_ms']} ms")
        print(f"    Tempo de processamento: {res['timing']['execution_time_ms']} ms")
        if res.get("result"):
            print(f"    Resposta (resumo): {res['result']['answer'][:120]}...")

    print("\n" + "=" * 60)
    print("2. MÉTRICAS DA FILA APÓS EXECUÇÃO DOS PRODUTORES E CONSUMIDORES")
    print("=" * 60)
    metrics = httpx.get(f"{API_BASE}/tasks/metrics").json()
    print(json.dumps(metrics, indent=2))

    print("\n" + "=" * 60)
    print("3. TESTE DE CACHE LRU: CONSULTAS REPETIDAS (HITS E MISSES)")
    print("=" * 60)
    # Primeira consulta (miss)
    q_test = "Como o mmap evita redundancia de copias de memoria?"
    print(f"Consulta 1 (Primeira vez - esperando MISS): '{q_test}'")
    t0 = time.time()
    r1 = httpx.post(f"{API_BASE}/query", json={"question": q_test, "use_cache": True}, timeout=60.0).json()
    dur1 = round((time.time() - t0) * 1000.0, 2)
    print(f"  Cache Hit: {r1.get('cache_hit')} | Tempo total: {dur1} ms | Timing RAG: {r1.get('timing')}")

    # Segunda consulta idêntica (hit imediato)
    print(f"\nConsulta 2 (Repetida - esperando HIT imediato): '{q_test}'")
    t0 = time.time()
    r2 = httpx.post(f"{API_BASE}/query", json={"question": q_test, "use_cache": True}, timeout=10.0).json()
    dur2 = round((time.time() - t0) * 1000.0, 2)
    print(f"  Cache Hit: {r2.get('cache_hit')} | Tempo total: {dur2} ms | Timing Cache: {r2.get('timing')}")

    print("\nEstatísticas do Cache após repetição:")
    c_stats = httpx.get(f"{API_BASE}/cache/stats").json()
    print(json.dumps(c_stats, indent=2))

    print("\n" + "=" * 60)
    print("4. TESTE DE EVICTION NO CACHE LRU (REDUÇÃO DE CAPACIDADE)")
    print("=" * 60)
    # Popula com outra chave
    httpx.post(f"{API_BASE}/query", json={"question": "O que sao minor page faults?", "use_cache": True}, timeout=60.0)
    keys_before = httpx.get(f"{API_BASE}/cache/keys").json()
    print(f"Chaves antes do redimensionamento (capacidade={keys_before['capacity']}, tamanho={keys_before['current_size']}):")
    print(f"  {keys_before['keys_lru_to_mru']}")

    # Reduz capacidade para 1 para forçar eviction do item menos recente
    print("\nReduzindo capacidade do cache para 1...")
    evict_res = httpx.post(f"{API_BASE}/cache/capacity", json={"capacity": 1}).json()
    print(f"Despejos imediatos realizados: {evict_res['items_evicted_now']}")

    keys_after = httpx.get(f"{API_BASE}/cache/keys").json()
    print(f"Chaves após redimensionamento (capacidade={keys_after['capacity']}, tamanho={keys_after['current_size']}):")
    print(f"  {keys_after['keys_lru_to_mru']}")
    c_stats_final = httpx.get(f"{API_BASE}/cache/stats").json()
    print(f"Estatísticas finais do cache: evictions={c_stats_final['evictions']}, hit_rate={c_stats_final['hit_rate']}")

if __name__ == "__main__":
    main()
