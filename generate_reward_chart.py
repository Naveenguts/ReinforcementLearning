from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    csv_path = Path(os.getenv("SUPPLY_CHAIN_EVAL_CSV", "evaluation_results.csv"))
    output_path = Path(os.getenv("SUPPLY_CHAIN_REWARD_PNG", "reward_chart.png"))

    rows = load_rows(csv_path)
    if not rows:
        raise RuntimeError(f"No rows found in {csv_path}")

    task_backend_rewards: Dict[str, Dict[str, float]] = defaultdict(dict)
    for row in rows:
        task_backend_rewards[str(row["task"])][str(row["backend"])] = float(row["final_reward"])

    tasks = ["steady_state", "port_strike", "black_swan"]
    labels = [task for task in tasks if task in task_backend_rewards]
    dummy_values = [task_backend_rewards[task].get("dummy", 0.0) for task in labels]
    hf_values = [task_backend_rewards[task].get("huggingface", 0.0) for task in labels]

    x = np.arange(len(labels))
    width = 0.36

    plt.figure(figsize=(9, 4.8))
    bars_dummy = plt.bar(x - width / 2, dummy_values, width, label="Dummy", color="#577590")
    bars_hf = plt.bar(x + width / 2, hf_values, width, label="Hugging Face", color="#2a9d8f")
    plt.axhline(0, color="#333333", linewidth=1)
    plt.title("Final Reward by Scenario: Dummy vs Hugging Face")
    plt.ylabel("Final reward")
    plt.xlabel("Scenario")
    plt.xticks(x, labels)
    plt.legend()
    plt.tight_layout()

    for bars in (bars_dummy, bars_hf):
        for bar in bars:
            value = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    plt.savefig(output_path, dpi=160)
    print(f"Reward chart written to {output_path}")


if __name__ == "__main__":
    main()
