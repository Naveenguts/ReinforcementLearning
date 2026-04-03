from __future__ import annotations

import json
import os
import re
import csv
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import requests
from pydantic import TypeAdapter

from models import Action

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoModelForSeq2SeqLM, AutoTokenizer
except Exception:  # pragma: no cover - optional dependency
    torch = None
    AutoModelForCausalLM = None
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None

warnings.filterwarnings(
    "ignore",
    message=r".*tie shared\.weight to lm_head\.weight.*",
)

ACTION_ADAPTER = TypeAdapter(Action)
PRESETS: Sequence[str] = ("steady_state", "port_strike", "black_swan")
BACKENDS: Sequence[str] = ("dummy", "huggingface")
HF_MODEL_NAME = os.getenv("SUPPLY_CHAIN_HF_MODEL", "google/flan-t5-small")


@dataclass
class EvalRow:
    backend: str
    task: str
    steps: int
    delivered: int
    late: int
    final_reward: float
    total_reward: float
    inventory_ok: bool
    done: bool


def build_prompt(
    state: Dict[str, Any],
    route_candidates: Dict[str, List[str]] | None = None,
    focus_order_id: str | None = None,
) -> str:
    formatted_state = format_state(state)
    candidate_text = ""
    if route_candidates:
        lines = ["Route candidates by order (model should pick only from these IDs):"]
        for order_id, candidates in route_candidates.items():
            if candidates:
                lines.append(f"- {order_id}: {', '.join(candidates)}")
        if len(lines) > 1:
            candidate_text = "\n" + "\n".join(lines) + "\n"

    focus_text = f"Focus order: {focus_order_id}\n" if focus_order_id else ""

    return (
        "You are a supply chain optimizer. "
        "CRITICAL RULES: "
        "Always prioritize orders with earliest due date. "
        "If delay risk exists, use expedite. "
        "If route blocked, reroute immediately. "
        "Avoid late deliveries at all cost. "
        "Return only JSON matching one action shape: "
        "{\"type\":\"wait\"} OR "
        "{\"type\":\"reroute\",\"order_id\":string,\"route_id\":string} OR "
        "{\"type\":\"expedite\",\"order_id\":string} OR "
        "{\"type\":\"adjust_stock\",\"warehouse_id\":string,\"amount\":positive_int}. "
        "State:\n"
        f"{focus_text}"
        f"{formatted_state}"
        f"{candidate_text}"
    )


def parse_action(text: str) -> Dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if not match:
            return {"type": "wait"}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"type": "wait"}

    try:
        action = ACTION_ADAPTER.validate_python(payload)
        return action.model_dump()
    except Exception:
        return {"type": "wait"}


def choose_dummy_action(state: Dict[str, Any]) -> Dict[str, Any]:
    routes = [r for r in state.get("routes", []) if r.get("status") != "blocked"]
    route_map = {(r.get("source"), r.get("destination")): r.get("id") for r in routes}
    pending_orders = [
        o
        for o in state.get("orders", [])
        if o.get("status") in {"pending", "late"}
    ]

    for order in pending_orders:
        route_id = route_map.get((order.get("origin"), order.get("destination")))
        if route_id:
            return {
                "type": "reroute",
                "order_id": order.get("id"),
                "route_id": route_id,
            }

    for warehouse in state.get("warehouses", []):
        stock = int(warehouse.get("stock", 0))
        capacity = int(warehouse.get("capacity", 0))
        if capacity > stock and stock < 20:
            return {
                "type": "adjust_stock",
                "warehouse_id": warehouse.get("id"),
                "amount": 10,
            }

    in_transit = [o for o in state.get("orders", []) if o.get("status") == "in_transit"]
    if in_transit:
        return {"type": "expedite", "order_id": in_transit[0].get("id")}

    return {"type": "wait"}


def _select_focus_order(state: Dict[str, Any]) -> Dict[str, Any] | None:
    pending_orders = [
        order
        for order in state.get("orders", [])
        if order.get("status") in {"pending", "late"}
    ]
    if not pending_orders:
        return None

    def sort_key(order: Dict[str, Any]) -> tuple[int, int, int]:
        late_priority = 0 if order.get("status") == "late" else 1
        due_date = int(order.get("due_date", 9999))
        quantity = int(order.get("quantity", 0))
        return (late_priority, due_date, -quantity)

    return sorted(pending_orders, key=sort_key)[0]


def _rank_route_candidates_for_order(order: Dict[str, Any], state: Dict[str, Any], limit: int = 2) -> List[str]:
    origin = order.get("origin")
    destination = order.get("destination")
    scored: List[tuple[float, str]] = []

    for route in state.get("routes", []):
        if route.get("status") == "blocked":
            continue
        if route.get("source") != origin:
            continue
        match_bonus = 0.0 if route.get("destination") == destination else 8.0
        score = float(route.get("lead_time", 999.0)) + float(route.get("cost", 999.0)) + match_bonus
        scored.append((score, str(route.get("id"))))

    scored.sort(key=lambda item: item[0])
    return [route_id for _, route_id in scored[:limit]]


def build_route_candidates(state: Dict[str, Any]) -> tuple[Dict[str, List[str]], str | None]:
    focus_order = _select_focus_order(state)
    if focus_order is None:
        return {}, None

    candidates: Dict[str, List[str]] = {}
    order_id = str(focus_order.get("id"))
    candidates[order_id] = _rank_route_candidates_for_order(focus_order, state)
    return candidates, order_id


def enforce_route_candidates(
    action: Dict[str, Any],
    route_candidates: Dict[str, List[str]],
    focus_order_id: str | None,
) -> Dict[str, Any]:
    if focus_order_id is None:
        return action

    allowed = route_candidates.get(focus_order_id, [])
    if not allowed:
        return action

    if action.get("type") != "reroute":
        return {
            "type": "reroute",
            "order_id": focus_order_id,
            "route_id": allowed[0],
        }

    if str(action.get("order_id", "")) != focus_order_id or str(action.get("route_id", "")) not in allowed:
        return {
            "type": "reroute",
            "order_id": focus_order_id,
            "route_id": allowed[0],
        }
    return action


def heuristic_action(state: Dict[str, Any]) -> Dict[str, Any] | None:
    low_stock_warehouses = [
        warehouse
        for warehouse in state.get("warehouses", [])
        if int(warehouse.get("stock", 0)) < 40 and int(warehouse.get("capacity", 0)) > int(warehouse.get("stock", 0))
    ]
    if low_stock_warehouses:
        warehouse = low_stock_warehouses[0]
        return {
            "type": "adjust_stock",
            "warehouse_id": warehouse.get("id"),
            "amount": 20,
        }

    return None


def emergency_override(state: Dict[str, Any]) -> Dict[str, Any] | None:
    current_step = int(state.get("time_step", 0))
    urgent_orders = [
        order
        for order in state.get("orders", [])
        if order.get("status") not in {"delivered", "cancelled"}
        and int(order.get("due_date", 9999)) <= current_step + 1
    ]
    if not urgent_orders:
        return None

    urgent_orders.sort(key=lambda order: (int(order.get("due_date", 9999)), -int(order.get("quantity", 0))))
    target = urgent_orders[0]
    return {
        "type": "expedite",
        "order_id": target.get("id"),
    }

def format_state(state: Dict[str, Any]) -> str:
    lines = [f"Task: {state.get('task_name', 'unknown')} | Step: {state.get('time_step', 0)}"]
    lines.append("Warehouses:")
    for warehouse in state.get("warehouses", []):
        lines.append(
            f"- {warehouse.get('id')}: stock={warehouse.get('stock')}/{warehouse.get('capacity')}"
        )

    lines.append("Routes:")
    for route in state.get("routes", []):
        lines.append(
            f"- {route.get('id')}: {route.get('source')}->{route.get('destination')} "
            f"lead={route.get('lead_time')} cost={route.get('cost')} status={route.get('status')}"
        )

    lines.append("Orders:")
    for order in state.get("orders", []):
        lines.append(
            f"- {order.get('id')}: {order.get('origin')}->{order.get('destination')} "
            f"qty={order.get('quantity')} due={order.get('due_date')} status={order.get('status')}"
        )

    events = state.get("active_events", [])
    if events:
        lines.append("Events:")
        for event in events:
            lines.append(f"- {event.get('type')}: {event.get('description')}")

    return "\n".join(lines)

class HuggingFaceAgent:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._tokenizer = None
        self._model = None
        self._seq2seq = _is_seq2seq_model(model_name)

    def choose_action(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if torch is None or AutoTokenizer is None:
            return choose_dummy_action(state)
        emergency = emergency_override(state)
        if emergency is not None:
            return safe_action(emergency, state)
        heuristic = heuristic_action(state)
        if heuristic is not None:
            return safe_action(heuristic, state)
        if self._tokenizer is None or self._model is None:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            if self._seq2seq:
                if AutoModelForSeq2SeqLM is None:
                    return choose_dummy_action(state)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
            else:
                if AutoModelForCausalLM is None:
                    return choose_dummy_action(state)
                self._model = AutoModelForCausalLM.from_pretrained(self.model_name)
            if hasattr(self._model, "config") and hasattr(self._model.config, "tie_word_embeddings"):
                self._model.config.tie_word_embeddings = False
            self._model.eval()
        route_candidates, focus_order_id = build_route_candidates(state)
        prompt = build_prompt(state, route_candidates, focus_order_id)
        inputs = self._tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            output_ids = self._model.generate(**inputs, max_new_tokens=64, do_sample=False)
        output = self._tokenizer.decode(output_ids[0], skip_special_tokens=True)
        action = safe_action(parse_action(output), state)
        return enforce_route_candidates(action, route_candidates, focus_order_id)


def _is_seq2seq_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return any(token in lowered for token in ("flan", "t5", "bart", "pegasus"))

def safe_action(action: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        validated = ACTION_ADAPTER.validate_python(action)
        return validated.model_dump()
    except Exception:
        return choose_dummy_action(state)

def run_episode(
    base_url: str,
    task: str,
    backend: str,
    max_steps: int,
    hf_agent: HuggingFaceAgent,
) -> EvalRow:
    state = requests.get(f"{base_url}/reset", params={"task": task}, timeout=30).json()
    total_reward = 0.0
    done = False
    steps = 0
    final_reward = 0.0

    for idx in range(max_steps):
        if backend == "dummy":
            action = choose_dummy_action(state)
        else:
            action = hf_agent.choose_action(state)

        result = requests.post(f"{base_url}/step", json=action, timeout=30).json()
        steps = idx + 1
        done = bool(result.get("done", False))
        reward = float(result.get("reward", {}).get("value", 0.0))
        total_reward += reward
        final_reward = reward
        state = result.get("observation", state)

        if done:
            break

    delivered = sum(1 for o in state.get("orders", []) if o.get("status") == "delivered")
    late = sum(1 for o in state.get("orders", []) if o.get("status") == "late")
    inventory_ok = all(int(w.get("stock", 0)) > 0 for w in state.get("warehouses", []))

    return EvalRow(
        backend=backend,
        task=task,
        steps=steps,
        delivered=delivered,
        late=late,
        final_reward=final_reward,
        total_reward=total_reward,
        inventory_ok=inventory_ok,
        done=done,
    )


def print_table(rows: List[EvalRow]) -> None:
    headers = [
        "backend",
        "task",
        "steps",
        "delivered",
        "late",
        "final_reward",
        "total_reward",
        "inventory_ok",
        "done",
    ]
    matrix = [
        [
            row.backend,
            row.task,
            str(row.steps),
            str(row.delivered),
            str(row.late),
            f"{row.final_reward:.2f}",
            f"{row.total_reward:.2f}",
            str(row.inventory_ok),
            str(row.done),
        ]
        for row in rows
    ]

    widths = [len(h) for h in headers]
    for line in matrix:
        for i, cell in enumerate(line):
            widths[i] = max(widths[i], len(cell))

    def fmt(line: List[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(line))

    print(fmt(headers))
    print("-+-".join("-" * w for w in widths))
    for line in matrix:
        print(fmt(line))


def write_csv(rows: List[EvalRow], output_path: str) -> None:
    fieldnames = [
        "backend",
        "task",
        "steps",
        "delivered",
        "late",
        "final_reward",
        "total_reward",
        "inventory_ok",
        "done",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "backend": row.backend,
                    "task": row.task,
                    "steps": row.steps,
                    "delivered": row.delivered,
                    "late": row.late,
                    "final_reward": f"{row.final_reward:.2f}",
                    "total_reward": f"{row.total_reward:.2f}",
                    "inventory_ok": row.inventory_ok,
                    "done": row.done,
                }
            )


def main() -> None:
    base_url = os.getenv("SUPPLY_CHAIN_BASE_URL", "http://127.0.0.1:8000")
    max_steps = int(os.getenv("SUPPLY_CHAIN_EVAL_STEPS", "20"))
    hf_model = os.getenv("SUPPLY_CHAIN_HF_MODEL", HF_MODEL_NAME)
    csv_path = os.getenv("SUPPLY_CHAIN_EVAL_CSV", "evaluation_results.csv")

    hf_agent = HuggingFaceAgent(hf_model)
    rows: List[EvalRow] = []

    for backend in BACKENDS:
        for task in PRESETS:
            rows.append(run_episode(base_url, task, backend, max_steps, hf_agent))

    print_table(rows)
    write_csv(rows, csv_path)
    print(f"CSV written to {csv_path}")


if __name__ == "__main__":
    main()
