# Supply Chain Chaos

Supply Chain Chaos is a graph-based supply chain environment with deterministic grading and a local Hugging Face agent. It is OpenEnv-compatible and evaluates AI agent behavior in logistics operations under uncertainty. The agent must route shipments, manage stock, and react to disruptions while balancing on-time delivery, cost, and carbon tradeoffs.

## Why This Is Useful

- Logistics planners regularly face dynamic constraints: blocked routes, delay cascades, and volatile fuel costs.
- Existing toy benchmarks do not capture order urgency, supply constraints, and operational penalties together.
- This environment provides a realistic testbed for measuring whether an AI agent is robust, not just correct in ideal conditions.
- The environment itself is what gets evaluated: the grader scores the resulting state and trajectory, not the prompt text.

## Environment Summary

- Domain: Multi-node supply chain planning.
- State: Warehouses, routes, orders, active disruptions, and carbon footprint.
- Actions: `wait`, `reroute`, `expedite`, `adjust_stock`.
- API: `reset()`, `step(action)`, `state()`, plus `grade()` for deterministic task scoring.
- Tasks: `steady_state` (easy), `port_strike` (medium), `black_swan` (hard).
- Default seed: `42` for reproducible resets and comparisons.

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
| `steady_state` | Easy | Delivery completeness, timeliness, normalized cumulative return | `0.5203` |
| `port_strike` | Medium | Rerouting resilience under blocked route and cost control | `0.9018` |
| `black_swan` | Hard | Graceful degradation under cascading disruptions | `0.3732` |

Baseline run snapshot:

- `steady_state`: delivered `3/3`, score `0.5203`.
- `port_strike`: delivered `4/4`, score `0.9018`.
- `black_swan`: delivered `2/5`, score `0.3732`.

These values show clear task difficulty progression.

## Evaluation Results

Same task presets and default seed (`42`) were used for both backends. The environment, not the prompt text, is the object being graded.

| backend | task | score | delivered | late | final reward | total reward | steps | done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dummy | steady_state | 0.5203 | 3 | 0 | 172.94 | 110.17 | 4 | True |
| dummy | port_strike | 0.9018 | 4 | 0 | 224.46 | 365.01 | 6 | True |
| dummy | black_swan | 0.3732 | 2 | 0 | 85.57 | 98.15 | 5 | True |
| huggingface | steady_state | 0.7452 | 3 | 0 | 182.59 | 222.61 | 4 | True |
| huggingface | port_strike | 1.0000 | 4 | 0 | 226.46 | 737.72 | 8 | True |
| huggingface | black_swan | 0.4109 | 2 | 0 | 0.00 | 135.89 | 20 | False |

At a glance, the local Hugging Face agent improves score on `steady_state` and `port_strike`, while `black_swan` remains the hardest case because the run hits the step limit before completing.

## Evaluation Protocol Against Realistic Baseline

Compare your RL agent against the deterministic heuristic baseline:

1. `GET /reset?task=<task_name>`
2. Run `inference.py` with `SUPPLY_CHAIN_AGENT_BACKEND=dummy` for baseline
3. Run your agent and record score
4. `GET /grade?task=<task_name>` for both
5. Compare scores: **Your agent should beat the heuristic to demonstrate value**
6. Repeat across all tasks with same seed/config

Recommended comparison metrics:

- Task score (`0.0-1.0`)
- Delivered and late orders
- Steps taken
- Normalized cumulative reward
- Failure rate (invalid/no-progress episodes)

For this repo, the fastest evidence is the generated [results.md](results.md) report.

## Baseline Approach: Production-Grade Heuristic

**The reference solution uses a deterministic logistics heuristic, not an AI model.** This is what real supply chain companies deploy:

**Why heuristics, not LLMs?**
- Supply chain software (SAP, Oracle, Flexport, JDA) uses rule-based engines, not black-box LLMs
- Deterministic execution is required for audit trails and explainability
- General-purpose LLMs lack domain training and cannot optimize supply chain tradeoffs reliably
- Heuristics are fast, reproducible, and trustworthy for operational use

**The dummy backend strategy:**
- Prioritizes urgent/late orders by due date and quantity
- Uses proactive expedite for near-deadline in-transit orders
- Applies stock replenishment from projected near-term demand
- Falls back gracefully if misconfigured
- Provides a deterministic fallback when Hugging Face is unavailable

**Baseline performance on deterministic graders:**
- `steady_state`: score `0.7338` (easy: all 3 orders delivered)
- `port_strike`: score `1.0000` (medium: resilience under blocked route)
- `black_swan`: score `0.1279` (hard: graceful degradation under cascades)

This approach provides a **credible, realistic baseline** for Phase 2 agent comparisons.

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

## Agent Backends

**Hackathon Constraint: Only dummy or huggingface backends are allowed.**

**Primary (Demo Default):**
- `SUPPLY_CHAIN_AGENT_BACKEND=huggingface`: Local LLM proof-of-concept using `google/flan-t5-small`

**Baseline:**
- `SUPPLY_CHAIN_AGENT_BACKEND=dummy`: Deterministic heuristic for comparison and fallback

Note: If the Hugging Face model fails to load, the runner automatically falls back to `dummy` to keep the demo reproducible.

## Environment Variables

Required:

- `API_BASE_URL`
- `API_KEY` (required for `SUPPLY_CHAIN_AGENT_BACKEND=huggingface`)

Optional:

- `SUPPLY_CHAIN_AGENT_BACKEND` (`huggingface` ← default, `dummy`)
- `SUPPLY_CHAIN_TASK` (default: `steady_state`)
- `SUPPLY_CHAIN_HF_MODEL` (default: `google/flan-t5-small`, HuggingFace only)
- `SUPPLY_CHAIN_MAX_STEPS` (default: `20`)

The environment defaults to seed `42` for deterministic grading and comparisons.

## Run Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start server with one command:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

3. Run the default demo inference:

```bash
export API_BASE_URL="http://127.0.0.1:8000"
export API_KEY="your-proxy-key"
export SUPPLY_CHAIN_AGENT_BACKEND="huggingface"
export SUPPLY_CHAIN_HF_MODEL="google/flan-t5-small"
python inference.py
```

Structured output follows strict format:

```text
[START] task=steady_state env=supply-chain-chaos model=google/flan-t5-small
[INFO] backend=huggingface model=google/flan-t5-small loaded=True
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
