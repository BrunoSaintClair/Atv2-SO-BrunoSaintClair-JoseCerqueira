"""Script para teste e validação da Condição de Corrida (Experimento D)."""

import json
import httpx

API_BASE = "http://localhost:8001"

def test_race_condition():
    print("=" * 70)
    print("EXPERIMENTO D: CONDIÇÃO DE CORRIDA VS SINCRONIZAÇÃO (LOCK)")
    print("=" * 70)

    payload = {
        "num_threads": 4,
        "increments_per_thread": 2000,
        "mode": "both",
        "repeat": 3,
        "inject_interleaving": True
    }

    print("Parâmetros do Experimento:")
    print(f"  Threads concorrentes: {payload['num_threads']}")
    print(f"  Incrementos por thread: {payload['increments_per_thread']}")
    print(f"  Total esperado por repetição: {payload['num_threads'] * payload['increments_per_thread']}")
    print(f"  Repetições por modo: {payload['repeat']}")
    print(f"  Modo de execução: {payload['mode']}")

    print("\nExecutando experimento via API (POST /experiments/race-condition)...")
    resp = httpx.post(f"{API_BASE}/experiments/race-condition", json=payload, timeout=60.0)
    
    if resp.status_code != 200:
        print(f"Erro na requisição: HTTP {resp.status_code} - {resp.text}")
        return

    data = resp.json()
    print("\n" + "-" * 70)
    print("RESULTADOS POR REPETIÇÃO (TRIALS):")
    print("-" * 70)
    print(f"{'Run':<4} | {'Modo':<16} | {'Esperado':<8} | {'Observado':<9} | {'Perdidos':<8} | {'Taxa Perda':<10} | {'Duração':<10}")
    print("-" * 70)

    for t in data["trials"]:
        mode_str = "Sincronizado (Lock)" if t["use_lock"] else "Sem Proteção (Race)"
        print(
            f"{t['run_id']:<4} | {mode_str:<16} | {t['expected_value']:<8} | {t['observed_value']:<9} | "
            f"{t['lost_updates']:<8} | {t['lost_ratio_percent']}%{'':<4} | {t['duration_ms']} ms"
        )

    print("\n" + "=" * 70)
    print("SUMÁRIO COMPARATIVO E TRADE-OFFS:")
    print("=" * 70)
    summary = data["comparison_summary"]
    unsync = summary["unsynchronized"]
    sync = summary["synchronized"]

    print(f"1. MODO SEM SINCRONIZAÇÃO:")
    print(f"   - Todas corretas: {unsync['all_correct']}")
    print(f"   - Média de incrementos perdidos: {unsync['average_lost_updates']} ({unsync['average_lost_ratio_percent']}%)")
    print(f"   - Duração média: {unsync['average_duration_ms']} ms")

    print(f"\n2. MODO COM SINCRONIZAÇÃO (Lock):")
    print(f"   - Todas corretas: {sync['all_correct']}")
    print(f"   - Média de incrementos perdidos: {sync['average_lost_updates']} ({sync['average_lost_ratio_percent']}%)")
    print(f"   - Duração média: {sync['average_duration_ms']} ms")

    if "trade_off" in summary:
        to = summary["trade_off"]
        print(f"\n3. ANÁLISE DE SISTEMAS OPERACIONAIS:")
        print(f"   - Sobrecarga de sincronização (overhead): +{to['lock_overhead_percent']}% no tempo")
        print(f"   - Garantia de corretude: {to['consistency_guarantee']}")

if __name__ == "__main__":
    test_race_condition()
