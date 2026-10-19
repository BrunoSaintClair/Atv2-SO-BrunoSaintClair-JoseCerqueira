"""Script de validação de saturação de fila cheia e escala dinâmica via endpoints HTTP."""

import json
import time
import httpx

API_BASE = "http://localhost:8001"

def test_scaling_and_full_queue():
    print("=" * 60)
    print("1. TESTE DE ESCALONAMENTO DE WORKERS VIA HTTP")
    print("=" * 60)
    
    # Escala para 4 workers
    r_scale4 = httpx.post(f"{API_BASE}/tasks/workers/scale", json={"num_workers": 4}).json()
    print(f"Workers escalados para 4: active_workers={r_scale4['active_workers']}")
    
    # Escala de volta para 1 worker para o teste de saturação
    r_scale1 = httpx.post(f"{API_BASE}/tasks/workers/scale", json={"num_workers": 1}).json()
    print(f"Workers escalados para 1: active_workers={r_scale1['active_workers']}")

    print("\n" + "=" * 60)
    print("2. TESTE DE SATURAÇÃO DE FILA (CAPACIDADE = 1)")
    print("=" * 60)
    
    # Ajusta a capacidade da fila para 1 via endpoint
    r_cap = httpx.post(f"{API_BASE}/tasks/capacity", json={"capacity": 1}).json()
    print(f"Capacidade da fila ajustada para: {r_cap['queue_metrics']['queue_capacity']}")

    # Tarefa 1: Imediatamente consumida pelo único worker
    print("\nSubmetendo Tarefa 1 (vai para processamento no worker)...")
    t1 = httpx.post(
        f"{API_BASE}/tasks/query",
        json={"question": "O que e paginacao no Linux?", "use_cache": False},
        timeout=5.0
    )
    print(f"Tarefa 1 status HTTP: {t1.status_code}")

    # Tarefa 2: Ocupa a única vaga da fila (capacidade = 1)
    print("Submetendo Tarefa 2 (ocupa a vaga única da fila)...")
    t2 = httpx.post(
        f"{API_BASE}/tasks/query",
        json={"question": "O que e memoria virtual?", "use_cache": False},
        timeout=5.0
    )
    print(f"Tarefa 2 status HTTP: {t2.status_code}")

    # Tarefa 3: A fila está cheia! O put() bloqueia e sofre timeout de 3s -> HTTP 503
    print("Submetendo Tarefa 3 (fila cheia -> esperando bloqueio e timeout de 3s)...")
    t_start = time.time()
    t3 = httpx.post(
        f"{API_BASE}/tasks/query",
        json={"question": "O que e swap?", "use_cache": False},
        timeout=10.0
    )
    t_wait = round((time.time() - t_start), 2)
    print(f"Tarefa 3 status HTTP: {t3.status_code} (esperou {t_wait}s)")
    print(f"Resposta do erro: {t3.json()}")

    print("\n" + "=" * 60)
    print("3. RESTAURAÇÃO DE CAPACIDADE E WORKERS")
    print("=" * 60)
    httpx.post(f"{API_BASE}/tasks/capacity", json={"capacity": 50})
    httpx.post(f"{API_BASE}/tasks/workers/scale", json={"num_workers": 2})
    final_metrics = httpx.get(f"{API_BASE}/tasks/metrics").json()
    print("Métricas finais da fila:")
    print(json.dumps(final_metrics, indent=2))

if __name__ == "__main__":
    test_scaling_and_full_queue()
