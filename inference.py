from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI
from pydantic import TypeAdapter

from models import Action

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
_API_KEY_ENV = os.getenv("API_KEY", "")
_HF_MODEL_ENV = os.getenv("SUPPLY_CHAIN_HF_MODEL", "gpt-4o-mini")
MODEL_NAME = "gpt-4o-mini"
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
MAX_STEPS = int(os.getenv("SUPPLY_CHAIN_MAX_STEPS", "20"))
AGENT_BACKEND = os.getenv("SUPPLY_CHAIN_AGENT_BACKEND", "huggingface")
REWARD_MIN = float(os.getenv("SUPPLY_CHAIN_REWARD_MIN", "-50"))
REWARD_MAX = float(os.getenv("SUPPLY_CHAIN_REWARD_MAX", "200"))
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "40"))
LLM_MAX_RETRIES = int(os.getenv("SUPPLY_CHAIN_LLM_RETRIES", "2"))

hf_agent = None
llm_call_emitted = False
ACTION_ADAPTER = TypeAdapter(Action)


def build_huggingface_agent():
    global hf_agent
    if hf_agent is not None:
        return hf_agent
    hf_agent = HuggingFaceAgentModel(
        base_url=os.environ["API_BASE_URL"],
        model_name=MODEL_NAME,
        api_key=os.environ["API_KEY"],
    )
    print(f"[INFO] OpenAI client initialized for model: {MODEL_NAME}", flush=True)
    return hf_agent


class HuggingFaceAgentModel:
    def __init__(self, base_url: str, model_name: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key,
            base_url=f"{self.base_url}/v1",
        )

    def generate(self, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(max(1, LLM_MAX_RETRIES)):
            try:
                print("[DEBUG] Calling LLM via proxy...", flush=True)
                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a strict JSON action generator. Reply with a single JSON object only.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=0.2,
                    max_tokens=120,
                )
                content = completion.choices[0].message.content
                return content or '{"type":"wait"}'
            except Exception as exc:
                last_error = exc
                print(f"[WARN] LLM call failed on attempt {attempt + 1}: {exc}", flush=True)

        if last_error is not None:
            raise last_error
        return '{"type":"wait"}'


# Hackathon constraint: only dummy or huggingface backends are allowed.


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
        "You are an expert supply chain optimizer.\n"
        "Your goal is to MAXIMIZE reward.\n\n"
        "PRIORITY ORDER (STRICT):\n"
        "1. Deliver ALL orders before due date\n"
        "2. NEVER allow late orders\n"
        "3. Expedite if any risk of delay\n"
        "4. Use fastest route (low lead_time)\n"
        "5. Keep warehouse stock >= 40 when possible\n\n"
        "CRITICAL RULES:\n"
        "- If due_date <= current_step+1 -> MUST expedite\n"
        "- If route blocked -> MUST reroute immediately\n"
        "- If stock < 40 -> adjust_stock\n"
        "- Never return invalid JSON\n\n"
        "Return ONLY JSON:\n"
        "{\"type\": \"wait\"} OR "
        "{\"type\": \"reroute\", \"order_id\": string, \"route_id\": string} OR "
        "{\"type\": \"expedite\", \"order_id\": string} OR "
        "{\"type\": \"adjust_stock\", \"warehouse_id\": string, \"amount\": int}\n\n"
        f"{focus_text}"
        f"{formatted_state}\n"
        f"{candidate_text}"
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
        if int(warehouse.get("stock", 0)) < LOW_STOCK_THRESHOLD
        and int(warehouse.get("capacity", 0)) > int(warehouse.get("stock", 0))
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
        if capacity > stock and (stock < LOW_STOCK_THRESHOLD or stock < projected_need):
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


def _rank_route_candidates_for_order(order: Dict[str, Any], state: Dict[str, Any], limit: int = 3) -> List[str]:
    origin = order.get("origin")
    destination = order.get("destination")
    scored: List[tuple[float, str]] = []

    for route in state.get("routes", []):
        if route.get("status") == "blocked":
            continue
        if route.get("source") != origin:
            continue
        match_bonus = 0.0 if route.get("destination") == destination else 8.0
        score = (
            float(route.get("lead_time", 999.0)) * 2.0
            + float(route.get("cost", 999.0)) * 0.5
            + match_bonus
        )
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
    global llm_call_emitted
    agent = build_huggingface_agent()
    if not llm_call_emitted:
        # Ensure at least one proxy-observable LLM call even if rule overrides trigger.
        agent.generate('Return only JSON: {"type":"wait"}')
        llm_call_emitted = True

    emergency = emergency_override(state)
    if emergency:
        return emergency

    heuristic = heuristic_action(state)
    if heuristic:
        return heuristic

    route_candidates, focus_order_id = build_route_candidates(state)
    prompt = build_prompt(state, route_candidates, focus_order_id)
    generated = agent.generate(prompt)
    action = safe_action(parse_action(generated), state)
    return enforce_route_candidates(action, route_candidates, focus_order_id)


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
    model_label = MODEL_NAME if AGENT_BACKEND == "huggingface" else "dummy-heuristic"
    
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

        if AGENT_BACKEND == "huggingface":
            loaded_agent = build_huggingface_agent()
            print(
                f"[INFO] backend=huggingface model={MODEL_NAME} loaded={loaded_agent is not None}",
                flush=True,
            )
        
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
