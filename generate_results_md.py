from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class Row:
    backend: str
    task: str
    steps: int
    delivered: int
    late: int
    final_reward: float
    total_reward: float
    inventory_ok: bool
    done: bool


def load_rows(csv_path: Path) -> List[Row]:
    rows: List[Row] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows.append(
                Row(
                    backend=str(raw["backend"]),
                    task=str(raw["task"]),
                    steps=int(raw["steps"]),
                    delivered=int(raw["delivered"]),
                    late=int(raw["late"]),
                    final_reward=float(raw["final_reward"]),
                    total_reward=float(raw["total_reward"]),
                    inventory_ok=str(raw["inventory_ok"]).lower() == "true",
                    done=str(raw["done"]).lower() == "true",
                )
            )
    return rows


def summarize(rows: List[Row]) -> str:
    if not rows:
        return "No evaluation rows were found."

    by_backend: Dict[str, List[Row]] = defaultdict(list)
    by_task: Dict[str, List[Row]] = defaultdict(list)
    for row in rows:
        by_backend[row.backend].append(row)
        by_task[row.task].append(row)

    total_rows = len(rows)
    avg_final_reward = sum(row.final_reward for row in rows) / total_rows
    avg_total_reward = sum(row.total_reward for row in rows) / total_rows
    total_delivered = sum(row.delivered for row in rows)
    total_late = sum(row.late for row in rows)
    inventory_ok_rate = sum(1 for row in rows if row.inventory_ok) / total_rows
    done_rate = sum(1 for row in rows if row.done) / total_rows

    lines = []
    lines.append(
        "This evaluation compared the dummy and Hugging Face baselines across the steady_state, port_strike, and black_swan presets. "
        f"Across {total_rows} runs, the average final reward was {avg_final_reward:.2f} and the average cumulative reward was {avg_total_reward:.2f}. "
        f"The runs delivered {total_delivered} orders in total, incurred {total_late} late orders, kept inventory positive in {inventory_ok_rate:.0%} of runs, and reached termination in {done_rate:.0%} of runs."
    )
    lines.append("")
    lines.append("Key points:")

    for backend, backend_rows in sorted(by_backend.items()):
        avg_reward = sum(row.final_reward for row in backend_rows) / len(backend_rows)
        avg_delivered = sum(row.delivered for row in backend_rows) / len(backend_rows)
        done_count = sum(1 for row in backend_rows if row.done)
        lines.append(
            f"- {backend}: average final reward {avg_reward:.2f}, average delivered {avg_delivered:.2f}, completed {done_count}/{len(backend_rows)} runs."
        )

    for task, task_rows in sorted(by_task.items()):
        best_row = max(task_rows, key=lambda row: row.final_reward)
        lines.append(
            f"- {task}: best final reward {best_row.final_reward:.2f} from {best_row.backend}, delivered {best_row.delivered}, late {best_row.late}."
        )

    return "\n".join(lines)


def main() -> None:
    csv_path = Path(os.getenv("SUPPLY_CHAIN_EVAL_CSV", "evaluation_results.csv"))
    output_path = Path(os.getenv("SUPPLY_CHAIN_RESULTS_MD", "results.md"))

    rows = load_rows(csv_path)
    report = summarize(rows)

    output_path.write_text(report + "\n", encoding="utf-8")
    print(f"Markdown report written to {output_path}")


if __name__ == "__main__":
    main()