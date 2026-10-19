"""Utilitário de exportação de dados brutos (CSV/JSON) e geração de gráficos com Matplotlib."""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import matplotlib

matplotlib.use("Agg")  # Garante renderização headless em servidores Linux
import matplotlib.pyplot as plt

from app.config import CSV_RESULTS_DIR, JSON_RESULTS_DIR, PLOTS_RESULTS_DIR


def export_experiment_data(
    experiment_code: str,
    parameters: Dict[str, Any],
    trials: List[Dict[str, Any]],
    summary: Dict[str, Any]
) -> Tuple[Path, Path]:
    """
    Exporta dados brutos do experimento para arquivos JSON e CSV padronizados.
    """
    base_name = experiment_code.lower()
    json_path = JSON_RESULTS_DIR / f"{base_name}.json"
    csv_path = CSV_RESULTS_DIR / f"{base_name}.csv"

    # 1. Exportação JSON completa
    full_data = {
        "experiment_code": experiment_code,
        "parameters": parameters,
        "summary": summary,
        "trials": trials
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_data, f, indent=2, ensure_ascii=False)

    # 2. Exportação CSV tabular dos trials
    if trials:
        fieldnames = list(trials[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trials:
                # Trata campos aninhados ou listas convertendo para string
                flat_row = {}
                for k, v in t.items():
                    if isinstance(v, (dict, list)):
                        flat_row[k] = json.dumps(v)
                    else:
                        flat_row[k] = v
                writer.writerow(flat_row)

    return json_path, csv_path


def generate_c1_c2_plot(trials: List[Dict[str, Any]]) -> Optional[Path]:
    """Gera gráfico comparativo entre Leitura Convencional (C1) e mmap (C2)."""
    if not trials:
        return None

    plot_path = PLOTS_RESULTS_DIR / "c1_c2_storage_comparison.png"
    
    # Agrupa por método
    c1_times = [t["duration_ms"] for t in trials if t.get("method") == "conventional"]
    c2_times = [t["duration_ms"] for t in trials if t.get("method") == "mmap"]
    
    if not c1_times or not c2_times:
        return None

    methods = ["C1: Convencional (read)", "C2: Mapeado (mmap)"]
    avg_times = [sum(c1_times) / len(c1_times), sum(c2_times) / len(c2_times)]

    fig, ax1 = plt.subplots(figsize=(8, 5))
    bars = ax1.bar(methods, avg_times, color=["#1f77b4", "#2ca02c"], width=0.45)
    ax1.set_ylabel("Tempo de Leitura (ms)")
    ax1.set_title("Comparação de Desempenho de E/S: read() vs mmap()")
    ax1.grid(axis="y", linestyle="--", alpha=0.7)

    # Adiciona rótulos numéricos sobre as barras
    for bar in bars:
        height = bar.get_height()
        ax1.annotate(
            f"{height:.2f} ms",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center", va="bottom", fontweight="bold"
        )

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    return plot_path


def generate_c3_plot(trials: List[Dict[str, Any]]) -> Optional[Path]:
    """Gera gráfico de escalabilidade e latência por número de workers (C3)."""
    if not trials:
        return None

    plot_path = PLOTS_RESULTS_DIR / "c3_concurrency_workers.png"

    # Agrupa por worker_count
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for t in trials:
        w = t["workers"]
        grouped.setdefault(w, []).append(t)

    sorted_workers = sorted(grouped.keys())
    throughputs = []
    avg_latencies = []

    for w in sorted_workers:
        runs = grouped[w]
        avg_tp = sum(r["throughput_tasks_per_sec"] for r in runs) / len(runs)
        avg_lat = sum(r["average_latency_ms"] for r in runs) / len(runs)
        throughputs.append(avg_tp)
        avg_latencies.append(avg_lat)

    fig, ax1 = plt.subplots(figsize=(9, 5))
    color = "#1f77b4"
    ax1.set_xlabel("Número de Workers Consumidores")
    ax1.set_ylabel("Vazão (tarefas/segundo)", color=color)
    line1 = ax1.plot(sorted_workers, throughputs, marker="o", color=color, linewidth=2, label="Vazão (tasks/s)")
    ax1.tick_params(axis="y", labelcolor=color)
    ax1.grid(True, linestyle="--", alpha=0.6)

    ax2 = ax1.twinx()
    color = "#d62728"
    ax2.set_ylabel("Latência Média (ms)", color=color)
    line2 = ax2.plot(sorted_workers, avg_latencies, marker="s", color=color, linewidth=2, linestyle="--", label="Latência Média (ms)")
    ax2.tick_params(axis="y", labelcolor=color)

    plt.title("Experimento C3: Escalabilidade da Fila Compartilhada (1, 2 e 4 Workers)")
    plt.xticks(sorted_workers)
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    return plot_path


def generate_c4_plot(trials: List[Dict[str, Any]]) -> Optional[Path]:
    """Gera gráfico de eficiência e taxa de acerto do Cache LRU (C4)."""
    if not trials:
        return None

    plot_path = PLOTS_RESULTS_DIR / "c4_cache_hit_rate.png"

    scenarios = [t["scenario_name"] for t in trials]
    hit_rates = [t["hit_rate"] * 100 for t in trials]
    latencies = [t["average_latency_ms"] for t in trials]

    x = range(len(scenarios))
    fig, ax1 = plt.subplots(figsize=(9, 5))

    ax1.bar([i - 0.2 for i in x], hit_rates, width=0.4, label="Taxa de Acerto (%)", color="#2ca02c")
    ax1.set_ylabel("Taxa de Acerto (%)", color="#2ca02c")
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, rotation=15, ha="right")
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    ax2 = ax1.twinx()
    ax2.plot(x, latencies, color="#ff7f0e", marker="o", linewidth=2.5, label="Latência Média (ms)")
    ax2.set_ylabel("Latência Média (ms)", color="#ff7f0e")

    plt.title("Experimento C4: Desempenho e Acertos do Cache Compartilhado")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    return plot_path


def generate_c5_plot(trials: List[Dict[str, Any]]) -> Optional[Path]:
    """Gera gráfico de ocupação de memória sob pressão controlada (C5)."""
    if not trials:
        return None

    plot_path = PLOTS_RESULTS_DIR / "c5_memory_pressure.png"

    alloc_mb = [t["requested_mb"] for t in trials]
    rss_during = [t["rss_during_mb"] for t in trials]
    rss_before = [t["rss_before_mb"] for t in trials]
    rss_after = [t["rss_after_mb"] for t in trials]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(alloc_mb))
    width = 0.25

    ax.bar([i - width for i in x], rss_before, width=width, label="RSS Antes", color="#7f7f7f")
    ax.bar(x, rss_during, width=width, label="RSS Durante (Pico)", color="#d62728")
    ax.bar([i + width for i in x], rss_after, width=width, label="RSS Após Coleta", color="#2ca02c")

    ax.set_xlabel("Alocação Solicitada (MB)")
    ax.set_ylabel("Resident Set Size (MB)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{m} MB" for m in alloc_mb])
    ax.set_title("Experimento C5: Comportamento da Memória Principal (RSS) sob Pressão")
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.legend()

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    return plot_path


def generate_c6_plot(trials: List[Dict[str, Any]]) -> Optional[Path]:
    """Gera gráfico de tolerância a falhas e recuperação (C6)."""
    if not trials:
        return None

    plot_path = PLOTS_RESULTS_DIR / "c6_fault_tolerance.png"

    scenarios = [t["scenario_name"] for t in trials]
    success_counts = [t.get("success_tasks", 0) for t in trials]
    failed_counts = [t.get("failed_tasks", 0) for t in trials]
    recovered_counts = [t.get("recovered_tasks", 0) for t in trials]

    x = range(len(scenarios))
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([i - width for i in x], success_counts, width=width, label="Sucesso Direto", color="#2ca02c")
    ax.bar(x, recovered_counts, width=width, label="Recuperadas via Retentativa", color="#1f77b4")
    ax.bar([i + width for i in x], failed_counts, width=width, label="Falhas Finais / Descarte", color="#d62728")

    ax.set_ylabel("Quantidade de Tarefas")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=10, ha="right")
    ax.set_title("Experimento C6: Tolerância a Falhas e Eficácia da Política de Retentativas")
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.legend()

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    return plot_path
