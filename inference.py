from __future__ import annotations

import json
import os
import re
import warnings
from typing import Any, Dict, List, Optional

import requests
from pydantic import TypeAdapter

from models import Action

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover - optional prototype dependency
    torch = None
    nn = None

try:
    from transformers import AutoModelForCausalLM, AutoModelForSeq2SeqLM, AutoTokenizer  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover - optional prototype dependency
    AutoModelForCausalLM = None
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None

warnings.filterwarnings(
    "ignore",
    message=r".*tie shared\.weight to lm_head\.weight.*",
)

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
HF_TOKEN = os.getenv("HF_TOKEN", "")
MAX_STEPS = int(os.getenv("SUPPLY_CHAIN_MAX_STEPS", "20"))
AGENT_BACKEND = os.getenv("SUPPLY_CHAIN_AGENT_BACKEND", "dummy")  # Hackathon: only dummy or huggingface allowed
HF_MODEL_NAME = os.getenv("SUPPLY_CHAIN_HF_MODEL", "google/flan-t5-small")
REWARD_MIN = float(os.getenv("SUPPLY_CHAIN_REWARD_MIN", "-50"))
REWARD_MAX = float(os.getenv("SUPPLY_CHAIN_REWARD_MAX", "200"))

hf_agent = None
ACTION_ADAPTER = TypeAdapter(Action)


class PolicyNet(nn.Module if nn is not None else object):
    def __init__(self, input_size: int = 16, output_size: int = 4) -> None:
        if nn is None:
            return
        super().__init__()
        self.fc1 = nn.Linear(input_size, 32)
        self.fc2 = nn.Linear(32, output_size)

    def forward(self, x):
        if nn is None:
            raise RuntimeError("PyTorch is not installed")
        x = torch.relu(self.fc1(x))
        return self.fc2(x)


def build_huggingface_agent():
    global hf_agent
    if hf_agent is not None:
        return hf_agent
    if AutoTokenizer is None or torch is None:
        return None
    hf_agent = HuggingFaceAgentModel(HF_MODEL_NAME)
    return hf_agent


def _is_seq2seq_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return any(token in lowered for token in ("flan", "t5", "bart", "pegasus"))


class HuggingFaceAgentModel:
    def __init__(self, model_name: str) -> None:
        if AutoTokenizer is None or torch is None:
            raise RuntimeError("transformers or torch is not installed")
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.seq2seq = _is_seq2seq_model(model_name)
        if self.seq2seq:
            if AutoModelForSeq2SeqLM is None:
                raise RuntimeError("Seq2Seq model class is unavailable")
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        else:
            if AutoModelForCausalLM is None:
                raise RuntimeError("Causal LM model class is unavailable")
            self.model = AutoModelForCausalLM.from_pretrained(model_name)
        if hasattr(self.model, "config") and hasattr(self.model.config, "tie_word_embeddings"):
            self.model.config.tie_word_embeddings = False
        self.model.eval()

    def generate(self, prompt: str) -> str:
        inputs = self.tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            output_ids = self.model.generate(**inputs, max_new_tokens=64, do_sample=False)
        return self.tokenizer.decode(output_ids[0], skip_special_tokens=True)


# OpenAI backend removed: hackathon constraint allows only dummy or huggingface


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
        "You are a supply chain optimizer.\n"
        "CRITICAL RULES:\n"
        "- Always prioritize orders with earliest due date.\n"
        "- If delay risk exists, use expedite.\n"
        "- If route blocked, reroute immediately.\n"
        "- Avoid late deliveries at all cost.\n"
        "Return only valid JSON that matches one of these safe action shapes:\n"
        "- {\"type\": \"wait\"}\n"
        "- {\"type\": \"reroute\", \"order_id\": string, \"route_id\": string}\n"
        "- {\"type\": \"expedite\", \"order_id\": string}\n"
        "- {\"type\": \"adjust_stock\", \"warehouse_id\": string, \"amount\": positive integer}\n"
        "State:\n"
        f"{focus_text}"
        f"{formatted_state}\n"
        f"{candidate_text}"
        "Choose the safest action that maximizes delivered orders and avoids blocked routes."
    )


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


def parse_action(text: str) -> Dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Hugging Face generation can include non-JSON preamble; recover first JSON object.
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


def safe_action(action: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        validated = ACTION_ADAPTER.validate_python(action)
        return validated.model_dump()
    except Exception:
        return choose_dummy_action(state)


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


def choose_dummy_action(state: Dict[str, Any]) -> Dict[str, Any]:
    current_step = int(state.get("time_step", 0))
    routes = [route for route in state.get("routes", []) if route.get("status") != "blocked"]

    def route_key(route: Dict[str, Any]) -> tuple[float, float]:
        return (float(route.get("lead_time", 999.0)), float(route.get("cost", 999.0)))

    pending_orders = [
        order
        for order in state.get("orders", [])
        if order.get("status") in {"pending", "late"}
    ]
    pending_orders.sort(
        key=lambda order: (
            0 if order.get("status") == "late" else 1,
            int(order.get("due_date", 9999)),
            -int(order.get("quantity", 0)),
        )
    )

    # Proactive expedite for in-transit orders close to due date.
    urgent_in_transit = [
        order
        for order in state.get("orders", [])
        if order.get("status") == "in_transit"
        and int(order.get("due_date", 9999)) <= current_step + 1
    ]
    if urgent_in_transit:
        urgent_in_transit.sort(key=lambda order: int(order.get("due_date", 9999)))
        return {"type": "expedite", "order_id": urgent_in_transit[0].get("id")}

    # Route highest-priority pending order through the best available candidate.
    for order in pending_orders:
        candidates = [
            route
            for route in routes
            if route.get("source") == order.get("origin")
        ]
        if not candidates:
            continue
        candidates.sort(key=route_key)
        best_route = candidates[0]
        return {
            "type": "reroute",
            "order_id": order.get("id"),
            "route_id": best_route.get("id"),
        }

    # Restock warehouses feeding near-due orders.
    needed_by_origin: Dict[str, int] = {}
    for order in pending_orders:
        if int(order.get("due_date", 9999)) <= current_step + 2:
            origin = str(order.get("origin"))
            needed_by_origin[origin] = needed_by_origin.get(origin, 0) + int(order.get("quantity", 0))

    for warehouse in state.get("warehouses", []):
        warehouse_id = str(warehouse.get("id"))
        stock = int(warehouse.get("stock", 0))
        capacity = int(warehouse.get("capacity", 0))
        projected_need = needed_by_origin.get(warehouse_id, 0)
        if capacity > stock and (stock < 40 or stock < projected_need):
            amount = max(10, min(capacity - stock, projected_need - stock if projected_need > stock else 20))
            return {
                "type": "adjust_stock",
                "warehouse_id": warehouse_id,
                "amount": amount,
            }

    in_transit = [order for order in state.get("orders", []) if order.get("status") == "in_transit"]
    if in_transit:
        in_transit.sort(key=lambda order: int(order.get("due_date", 9999)))
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


def choose_action(state: Dict[str, Any]) -> Dict[str, Any]:
    """Choose action using allowed backends: dummy or huggingface (per hackathon constraint)."""
    if AGENT_BACKEND == "dummy":
        return choose_dummy_action(state)

    if AGENT_BACKEND == "huggingface":
        emergency = emergency_override(state)
        if emergency is not None:
            return safe_action(emergency, state)

        heuristic = heuristic_action(state)
        if heuristic is not None:
            return safe_action(heuristic, state)

        agent = build_huggingface_agent()
        if agent is not None:
            route_candidates, focus_order_id = build_route_candidates(state)
            prompt = build_prompt(state, route_candidates, focus_order_id)
            generated = agent.generate(prompt)
            action = safe_action(parse_action(generated), state)
            return enforce_route_candidates(action, route_candidates, focus_order_id)
        # HuggingFace model failed to load; fall back to dummy
        return choose_dummy_action(state)

    # Unknown backend or none set; fall back to dummy (safe default)
    return choose_dummy_action(state)


def log_start(task: str, env: str, model: str) -> None:
    """Emit [START] line per Meta spec."""
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    """Emit [STEP] line per Meta spec."""
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, rewards: List[float]) -> None:
    """Emit [END] line per Meta spec."""
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}", flush=True)


def action_to_string(action: Dict[str, Any]) -> str:
    """Convert action dict to a string representation for logging."""
    action_type = action.get("type", "unknown")
    if action_type == "wait":
        return "wait()"
    elif action_type == "reroute":
        order_id = action.get("order_id", "?")
        route_id = action.get("route_id", "?")
        return f"reroute('{order_id}','{route_id}')"
    elif action_type == "expedite":
        order_id = action.get("order_id", "?")
        return f"expedite('{order_id}')"
    elif action_type == "adjust_stock":
        warehouse_id = action.get("warehouse_id", "?")
        amount = action.get("amount", "?")
        return f"adjust_stock('{warehouse_id}',{amount})"
    else:
        return f"action({action})"


def normalize_reward(raw_reward: float) -> float:
    """Normalize raw reward into [0.0, 1.0] for logging compliance."""
    if REWARD_MAX <= REWARD_MIN:
        return 0.0
    normalized = (raw_reward - REWARD_MIN) / (REWARD_MAX - REWARD_MIN)
    return max(0.0, min(1.0, normalized))


def is_success_state(state: Dict[str, Any]) -> bool:
    """Episode is successful when all orders are delivered and none are late."""
    orders = state.get("orders", [])
    if not orders:
        return False
    delivered = sum(1 for order in orders if order.get("status") == "delivered")
    late = sum(1 for order in orders if order.get("status") == "late")
    return delivered == len(orders) and late == 0


def main() -> None:
    """Main entry point following Meta's [START] [STEP] [END] format."""
    task_name = os.getenv("SUPPLY_CHAIN_TASK", "steady_state")
    benchmark_name = os.getenv("SUPPLY_CHAIN_BENCHMARK", "supply-chain-chaos")
    model_label = HF_MODEL_NAME if AGENT_BACKEND == "huggingface" else MODEL_NAME
    
    log_start(task=task_name, env=benchmark_name, model=model_label)
    
    rewards: List[float] = []
    steps_taken = 0
    success = False
    last_error: Optional[str] = None
    
    try:
        # Reset and get initial state
        reset_response = requests.get(f"{BASE_URL}/reset?task={task_name}", timeout=30)
        reset_response.raise_for_status()
        state = reset_response.json()
        
        # Main loop
        for step in range(1, MAX_STEPS + 1):
            try:
                # Choose action
                action = choose_action(state)
                action_str = action_to_string(action)
                
                # Step environment
                step_response = requests.post(f"{BASE_URL}/step", json=action, timeout=30)
                step_response.raise_for_status()
                result = step_response.json()
                
                # Extract and normalize reward for Meta-compliant logging.
                raw_reward = float(result.get("reward", {}).get("value", 0.0))
                reward_value = normalize_reward(raw_reward)
                done = result.get("done", False)
                error = None
                
                rewards.append(reward_value)
                steps_taken = step
                
                # Log step
                log_step(step=step, action=action_str, reward=reward_value, done=done, error=error)
                
                # Update state
                state = result.get("observation", state)
                
                # Check if episode is done
                if done:
                    break
                    
            except Exception as step_error:
                last_error = str(step_error)
                log_step(
                    step=step,
                    action="error",
                    reward=0.0,
                    done=True,
                    error=last_error
                )
                break
        
        # Determine success from final delivery outcomes.
        success = is_success_state(state)
        
    except Exception as exc:
        last_error = str(exc)
        success = False
    
    finally:
        # Always emit [END]
        log_end(success=success, steps=steps_taken, rewards=rewards)


if __name__ == "__main__":
    main()
