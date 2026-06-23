#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CONDITIONS = ["none", "D1", "D2"]


def load_asr_table(path: str) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            table.setdefault(row["attack_id"], {})[row["condition"]] = float(row["asr"])
    return table


def latest_asr_summary(results_dir: str = "results") -> str:
    candidates = sorted(Path(results_dir).glob("asr_summary_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No asr_summary_*.csv found in {results_dir}")
    return str(candidates[-1])


def plot_heatmap(table: dict[str, dict[str, float]], path: str) -> None:
    attacks = list(table.keys())
    data = [[table[a].get(c, 0.0) for c in CONDITIONS] for a in attacks]

    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(data, cmap="Reds", vmin=0.0, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(CONDITIONS)), labels=CONDITIONS)
    ax.set_yticks(range(len(attacks)), labels=attacks)
    ax.set_xlabel("Defense condition")
    ax.set_ylabel("Attack")
    ax.set_title("Attack Success Rate (ASR) by attack and defense")

    for i in range(len(attacks)):
        for j in range(len(CONDITIONS)):
            ax.text(j, i, f"{data[i][j]:.2f}", ha="center", va="center", color="black")

    fig.colorbar(im, ax=ax, label="ASR")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_grouped_bars(table: dict[str, dict[str, float]], path: str) -> None:
    attacks = list(table.keys())
    bar_width = 0.25
    x = range(len(attacks))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for i, condition in enumerate(CONDITIONS):
        offsets = [xi + (i - 1) * bar_width for xi in x]
        values = [table[a].get(condition, 0.0) for a in attacks]
        ax.bar(offsets, values, width=bar_width, label=condition)

    ax.set_xticks(list(x), labels=attacks)
    ax.set_ylabel("ASR")
    ax.set_xlabel("Attack")
    ax.set_title("ASR by attack, grouped by defense condition")
    ax.set_ylim(0.0, 1.0)
    ax.legend(title="Defense")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=None, help="Path to asr_summary_*.csv")
    args = parser.parse_args()

    summary_path = args.path or latest_asr_summary()
    table = load_asr_table(summary_path)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    heatmap_path = f"results/asr_heatmap_{ts}.png"
    bars_path = f"results/asr_bars_{ts}.png"

    plot_heatmap(table, heatmap_path)
    plot_grouped_bars(table, bars_path)
    print(f"Loaded {summary_path}")
    print(f"Wrote {heatmap_path}")
    print(f"Wrote {bars_path}")


if __name__ == "__main__":
    main()
