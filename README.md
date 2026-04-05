# Supply Chain Chaos

Supply Chain Chaos is an OpenEnv-compatible environment for evaluating AI agent behavior in logistics operations under uncertainty. The agent must route shipments, manage stock, and react to disruptions while balancing on-time delivery, cost, and carbon tradeoffs.

## Why This Is Useful

- Logistics planners regularly face dynamic constraints: blocked routes, delay cascades, and volatile fuel costs.
- Existing toy benchmarks do not capture order urgency, supply constraints, and operational penalties together.
- This environment provides a realistic testbed for measuring whether an AI agent is robust, not just correct in ideal conditions.

## Environment Summary

- Domain: Multi-node supply chain planning.
- State: Warehouses, routes, orders, active disruptions, and carbon footprint.
- Actions: `wait`, `reroute`, `expedite`, `adjust_stock`.
- API: `reset()`, `step(action)`, `state()`, plus `grade()` for deterministic task scoring.
- Tasks: `steady_state` (easy), `port_strike` (medium), `black_swan` (hard).

## Action Space

- `wait`: no-op for one step.
- `reroute(order_id, route_id)`: assign an order to a route and start movement.
- `expedite(order_id)`: increase shipment speed with cost/carbon tradeoff.
- `adjust_stock(warehouse_id, amount)`: replenish warehouse inventory.

## Observation Space

- `warehouses`: stock/capacity by node.
- `routes`: connectivity, lead time, cost, and status.
- `orders`: demand, due dates, route assignment, and progress.
- `active_events`: route blocks, demand spikes, fuel surges, supplier delays, customs holds, warehouse outages.
- `time_step`, `carbon_footprint`.

## Reward Design

Reward is dense (not sparse) and includes partial progress:

- Positive signal: delivered orders, completion bonuses.
- Penalties: operating cost, lateness, storage, carbon, and disruption impact.
- Anti-loop pressure: undelivered orders and delay accumulation reduce return over time.

This design provides meaningful trajectory feedback and discourages stalling/destructive behavior.

## Domain Realism Additions

Beyond baseline disruptions, the environment models:

- Supplier delays: route lead-time inflation and congestion effects.
- Customs holds: in-transit progress rollback.
- Warehouse outages: inventory losses and outbound congestion.
- Carbon-aware tradeoffs: explicit carbon penalties and expedite cost multipliers.

## Tasks, Graders, and Baseline Evidence

Graders are deterministic and return scores in `[0.0, 1.0]`.

| Task | Difficulty | Grader Measures | Deterministic Baseline (dummy backend) |
| --- | --- | --- | --- |
| `steady_state` | Easy | Delivery completeness, timeliness, normalized cumulative return | `0.7338` |
| `port_strike` | Medium | Rerouting resilience under blocked route and cost control | `1.0000` |
| `black_swan` | Hard | Graceful degradation under cascading disruptions | `0.1279` |

Baseline run snapshot:

- `steady_state`: delivered `3/3`, score `0.73`.
- `port_strike`: delivered `4/4`, score `1.00`.
- `black_swan`: delivered `1/5`, score `0.13`.

These values show clear task difficulty progression.

## Evaluation Protocol

Use a reproducible evaluation sequence:

1. `GET /reset?task=<task_name>`
2. Run `inference.py` with fixed backend/config
3. `GET /grade?task=<task_name>`
4. Repeat across all tasks with same seed/config

Recommended comparison metrics:

- Task score (`0.0-1.0`)
- Delivered and late orders
- Steps taken
- Normalized cumulative reward
- Failure rate (invalid/no-progress episodes)

## Strong Baseline Policy

The deterministic baseline is stronger than a naive rule set:

- Prioritizes urgent/late orders by due date and quantity.
- Uses proactive expedite for near-deadline in-transit orders.
- Applies stock replenishment from projected near-term demand.
- Falls back safely when model calls fail.

This provides a credible baseline for Phase 2 comparisons.

## Expected Failure Modes and Anti-Hack Protections

Expected failure modes:

- Over-expediting can reduce lateness but increase cost/carbon penalties.
- Greedy rerouting can produce downstream congestion under black swan conditions.
- Understocked warehouses can create late cascades.

How grading avoids trivial hacks:

- Score is not binary and not a single metric.
- Delivery count alone cannot maximize score because late/cost penalties remain.
- High-reward spikes are moderated by normalized task-specific grading.
- Hard task rewards graceful degradation, not exploit-heavy shortcuts.

## OpenEnv and Deployment Compliance

- Typed Pydantic models for `Observation`, `Action`, and `Reward`.
- Full API implementation: `step`, `reset`, `state`, and `grade`.
- `openenv.yaml` includes metadata, tasks, spaces, and validation details.
- Dockerized for Hugging Face Spaces.

## Environment Variables

Required:

- `API_BASE_URL`
- `MODEL_NAME`
- `HF_TOKEN`

Optional:

- `SUPPLY_CHAIN_AGENT_BACKEND` (`dummy`, `openai`, `huggingface`)
- `SUPPLY_CHAIN_TASK`
- `SUPPLY_CHAIN_HF_MODEL`
- `SUPPLY_CHAIN_MAX_STEPS`

## Run Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start server:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

3. Run baseline inference:

```bash
export API_BASE_URL="http://127.0.0.1:8000"
export MODEL_NAME="dummy-model"
export SUPPLY_CHAIN_AGENT_BACKEND="dummy"
python inference.py
```

Structured output follows strict format:

```text
[START] task=steady_state env=supply-chain-chaos model=dummy-model
[STEP] step=1 action=... reward=0.12 done=false error=null
[END] success=true steps=4 rewards=...
```

## Repository Files

- `env.py`: environment dynamics and reward shaping.
- `models.py`: typed schemas and presets.
- `server.py`: API endpoints.
- `graders.py`: deterministic task graders.
- `inference.py`: baseline agent runner.
- `openenv.yaml`: OpenEnv metadata and validation constraints.
