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
    print_header("VERIFICAÇÃO DE DOWNLOAD DE ARTEFATOS E AMOSTRAS (API REST)")
    for code in ["c1_c2", "c3", "c4", "c5", "c6"]:
        plot_resp = client.get(f"{BASE_URL}/experiments/{code}/plot")
        csv_resp = client.get(f"{BASE_URL}/experiments/{code}/csv")
        samples_resp = client.get(f"{BASE_URL}/experiments/{code}/samples?limit=5")
        samples_csv_resp = client.get(f"{BASE_URL}/experiments/{code}/samples/csv")
        print(f"  - Experimento [{code.upper()}]: "
              f"Plot = {plot_resp.status_code} ({len(plot_resp.content)} B) | "
              f"CSV = {csv_resp.status_code} ({len(csv_resp.content)} B) | "
              f"Amostras JSON = {samples_resp.status_code} ({len(samples_resp.json()) if samples_resp.status_code == 200 else 0} itens) | "
              f"Amostras CSV = {samples_csv_resp.status_code} ({len(samples_csv_resp.content)} B)")


def verify_system_telemetry(client: httpx.Client):
    print_header("VERIFICAÇÃO DA INSTRUMENTAÇÃO NATIVA DO LINUX (/system)")
    
    # 1. Informações do Ambiente
    info_resp = client.get(f"{BASE_URL}/system/info")
    info_resp.raise_for_status()
    info = info_resp.json()
    print("[Ambiente /system/info]:")
    print(f"  - SO: {info['operating_system'].get('distribution', info['operating_system']['system'])} | Kernel: {info['operating_system']['kernel']} | Arq: {info['operating_system']['architecture']}")
    print(f"  - CPU: {info['cpu']['model_name']} ({info['cpu']['physical_cores']} núcleos físicos, {info['cpu']['logical_cpus']} CPUs lógicas)")
    print(f"  - RAM Total: {info['memory_ram']['total_gb']} GB | Livre: {info['memory_ram']['free_gb']} GB | Disponível: {info['memory_ram']['available_gb']} GB")
    print(f"  - Swap Total: {info['memory_swap']['total_gb']} GB | Usado: {info['memory_swap']['used_gb']} GB")
    print(f"  - GPU: {info['gpu']['model']} ({info['gpu']['memory_total_mb']} MB VRAM) - Disponível: {info['gpu']['available']}")

    # 2. Detalhes de Memória (/proc/meminfo)
    mem_resp = client.get(f"{BASE_URL}/system/memory")
    mem_resp.raise_for_status()
    mem = mem_resp.json()
    print("\n[Memória Linux /system/memory]:")
    s = mem["summary"]
    print(f"  - MemFree: {s['mem_free_mb']} MB | MemAvailable: {s['mem_available_mb']} MB")
    print(f"  - Buffers: {s['buffers_mb']} MB | Cached (Page Cache): {s['cached_mb']} MB")
    print(f"  - SwapCached: {s['swap_cached_mb']} MB | Swap Usado: {s['swap_used_mb']} MB")

    # 3. Processo e I/O (/proc/[pid]/io e getrusage)
    proc_resp = client.get(f"{BASE_URL}/system/process")
    proc_resp.raise_for_status()
    proc = proc_resp.json()
    print("\n[Processo /system/process]:")
    print(f"  - PID: {proc['process_identification']['pid']} ({proc['process_identification']['name']}) | Status: {proc['process_identification']['status']}")
    print(f"  - RSS (Física): {proc['memory']['rss_mb']} MB | VSZ (Virtual): {proc['memory']['vsz_mb']} MB | Threads: {proc['concurrency']['num_threads']}")
    print(f"  - Minor Page Faults (RAM): {proc['page_faults']['minor_faults']} | Major (Disco): {proc['page_faults']['major_faults']}")
    print(f"  - I/O User-Space (rchar): {proc['io_counters']['rchar']} B | I/O Físico (read_bytes): {proc['io_counters']['read_bytes']} B")

    # 4. Armazenamento e Partições
    st_resp = client.get(f"{BASE_URL}/system/storage")
    st_resp.raise_for_status()
    st = st_resp.json()
    print("\n[Armazenamento /system/storage]:")
    for part in st["partitions"][:2]:
      print(f"  - Ponto de Montagem '{part['mountpoint']}': {part['total_gb']} GB total, {part['free_gb']} GB livre ({part['fstype']})")
    print("  - Arquivos da Aplicação:")
    for f in st["application_data_files"]:
      print(f"    * {f['name']}: {f['size_mb']} MB (Existe: {f['exists']})")


if __name__ == "__main__":
    with httpx.Client(timeout=60.0) as client:
        check_server(client)
        verify_system_telemetry(client)
        run_c1_c2(client)
        run_c3(client)
        run_c4(client)
        run_c5(client)
        run_c6(client)
        verify_artifacts(client)
    print_header("TODOS OS EXPERIMENTOS E INSTRUMENTAÇÃO VALIDADOS COM SUCESSO!")
