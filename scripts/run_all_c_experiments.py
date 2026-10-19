"""Script de automação e execução real de todos os experimentos acadêmicos C1–C6 e D."""

import json
import sys
import time
from typing import Any, Dict
import httpx

BASE_URL = "http://localhost:8001"


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_server(client: httpx.Client):
    print("Verificando disponibilidade do servidor em", BASE_URL, "...")
    try:
        resp = client.get(f"{BASE_URL}/health")
        resp.raise_for_status()
        print("Servidor operacional:", resp.json())
    except Exception as err:
        print(f"ERRO: Não foi possível conectar ao servidor: {err}")
        sys.exit(1)


def run_c1_c2(client: httpx.Client):
    print_header("EXPERIMENTO C1 e C2: Armazenamento (read convencional vs mmap)")
    payload = {
        "file_size_mb": 10,
        "chunk_size_kb": 64,
        "repeat": 3
    }
    resp = client.post(f"{BASE_URL}/experiments/c1-c2-compare", json=payload)
    resp.raise_for_status()
    data = resp.json()

    print("\n[C1 - Leitura Convencional open/read]")
    c1 = data["summary"]["conventional"]
    print(f"  - Duração Média: {c1['average_duration_ms']:.2f} ms")
    print(f"  - Vazão Média: {c1['average_throughput_mb_s']:.2f} MB/s")
    print(f"  - Faltas de Página Menores (ru_minflt): {c1['average_minor_faults']}")

    print("\n[C2 - Mapeamento de Memória mmap.mmap]")
    c2 = data["summary"]["mmap"]
    print(f"  - Duração Média: {c2['average_duration_ms']:.2f} ms")
    print(f"  - Vazão Média: {c2['average_throughput_mb_s']:.2f} MB/s")
    print(f"  - Faltas de Página Menores (ru_minflt): {c2['average_minor_faults']}")

    if "comparison" in data["summary"]:
        comp = data["summary"]["comparison"]
        print(f"\n[Comparação]: Diferença de tempo mmap vs convencional: {comp['mmap_vs_conventional_duration_diff_percent']}%")
        print(f"Interpretação SO: {comp['interpretation']}")

    print(f"Artefatos gerados: {data['artifacts']}")
    return data


def run_c3(client: httpx.Client):
    print_header("EXPERIMENTO C3: Concorrência na Fila Compartilhada (1, 2 e 4 Workers)")
    payload = {
        "workers_list": [1, 2, 4],
        "tasks_per_trial": 20,
        "queue_capacity": 10,
        "work_ms": 15.0,
        "repeat": 3
    }
    resp = client.post(f"{BASE_URL}/experiments/c3-concurrency", json=payload)
    resp.raise_for_status()
    data = resp.json()

    print("\nResultados de Escalabilidade:")
    for w in [1, 2, 4]:
        key = f"{w}_workers"
        if key in data["summary"]:
            s = data["summary"][key]
            print(f"  - [{w} Workers]: Vazão = {s['average_throughput_tasks_sec']} tasks/s | "
                  f"Latência Média = {s['average_latency_ms']} ms | "
                  f"Espera na Fila = {s['average_queue_wait_ms']} ms | "
                  f"Speedup vs 1 Worker = {s['speedup_vs_1_worker']}x")

    print(f"Artefatos gerados: {data['artifacts']}")
    return data


def run_c4(client: httpx.Client):
    print_header("EXPERIMENTO C4: Eficiência do Cache Compartilhado LRU")
    payload = {
        "cache_capacity": 10,
        "distinct_queries_count": 10,
        "repeat_queries_count": 10,
        "work_ms": 15.0,
        "repeat": 3
    }
    resp = client.post(f"{BASE_URL}/experiments/c4-cache", json=payload)
    resp.raise_for_status()
    data = resp.json()

    print("\nResultados do Cache por Cenário:")
    for scn_key, s in data["summary"].items():
        print(f"  - [{s['scenario']}]: Latência Média = {s['average_latency_ms']} ms | "
              f"Hit Rate = {s['average_hit_rate']*100:.1f}% | "
              f"Evicções = {s['average_evictions']} | "
              f"Economia de Tempo = {s['average_saved_percent']}%")

    print(f"Artefatos gerados: {data['artifacts']}")
    return data


def run_c5(client: httpx.Client):
    print_header("EXPERIMENTO C5: Impacto de Memória sob Pressão Controlada")
    payload = {
        "allocation_steps_mb": [100, 250, 500],
        "hold_duration_sec": 0.5,
        "repeat": 3
    }
    resp = client.post(f"{BASE_URL}/experiments/c5-memory-pressure", json=payload)
    resp.raise_for_status()
    data = resp.json()

    print("\nResultados de Memória Principal (RSS/Paging):")
    for step_mb in [100, 250, 500]:
        key = f"{step_mb}mb"
        if key in data["summary"]:
            s = data["summary"][key]
            print(f"  - [Alocação {step_mb} MB]: Pico RSS Médio = {s['average_peak_rss_mb']} MB | "
                  f"RSS Pós-GC = {s['average_after_rss_mb']} MB | "
                  f"Minor Page Faults = {s['average_minor_faults']} | "
                  f"Desalocação Eficiente = {s['rss_released_efficiently']}")

    print(f"Artefatos gerados: {data['artifacts']}")
    return data


def run_c6(client: httpx.Client):
    print_header("EXPERIMENTO C6: Tolerância a Falhas e Recuperação")
    payload = {
        "faulty_tasks_count": 10,
        "healthy_tasks_count": 10,
        "max_retries": 2,
        "repeat": 3
    }
    resp = client.post(f"{BASE_URL}/experiments/c6-fault-tolerance", json=payload)
    resp.raise_for_status()
    data = resp.json()

    print("\nResultados de Resiliência:")
    for scn_key, s in data["summary"].items():
        print(f"  - [{s['scenario']}]: Sucesso Médio = {s['average_success_tasks']} | "
              f"Recuperadas via Retry = {s['average_recovered_tasks']} | "
              f"Falhas Finais = {s['average_failed_tasks']} | "
              f"Pool de Workers Íntegro = {s['all_workers_survived']} | "
              f"Fila Consistente = {s['queue_consistency_preserved']}")

    print(f"Artefatos gerados: {data['artifacts']}")
    return data


def verify_artifacts(client: httpx.Client):
    print_header("VERIFICAÇÃO DE DOWNLOAD DE ARTEFATOS (API REST)")
    for code in ["c1_c2", "c3", "c4", "c5", "c6"]:
        plot_resp = client.get(f"{BASE_URL}/experiments/{code}/plot")
        csv_resp = client.get(f"{BASE_URL}/experiments/{code}/csv")
        print(f"  - Experimento [{code.upper()}]: Plot status = {plot_resp.status_code} ({len(plot_resp.content)} bytes) | "
              f"CSV status = {csv_resp.status_code} ({len(csv_resp.content)} bytes)")


if __name__ == "__main__":
    with httpx.Client(timeout=60.0) as client:
        check_server(client)
        run_c1_c2(client)
        run_c3(client)
        run_c4(client)
        run_c5(client)
        run_c6(client)
        verify_artifacts(client)
    print_header("TODOS OS EXPERIMENTOS EXECUTADOS E VALIDADOS COM SUCESSO!")
