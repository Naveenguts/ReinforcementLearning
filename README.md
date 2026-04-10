# Supply Chain Chaos

Supply Chain Chaos is an OpenEnv-compatible logistics benchmark that evaluates whether an agent can make robust decisions under disruption, not just solve idealized routing.

This project combines:
- A deterministic, gradeable simulation environment.
- A hybrid policy (rule-based safeguards + LLM action selection).
- Strict hackathon-compliant inference logging and proxy usage.

## Why This Project Is Shortlist-Worthy

- Real operations focus: on-time delivery, disruption handling, stock resilience, cost and carbon tradeoffs.
- Deterministic evaluation: reproducible graders with scores in [0.0, 1.0].
- Transparent agent design: clear safety overrides before model policy.
- Deployment-ready packaging: Dockerized API with typed schemas and OpenEnv metadata.
- Compliance-oriented inference runner: strict [START]/[STEP]/[END] format.

## Problem Framing

The environment models a multi-node supply chain with dynamic failures:
- Blocked routes
- Demand spikes
- Supplier delays
- Customs holds
- Warehouse outages
- Fuel and carbon pressure

Actions are constrained to realistic operations:
- wait
- reroute(order_id, route_id)
- expedite(order_id)
- adjust_stock(warehouse_id, amount)

## Agent Strategy

The policy is a hybrid controller:
- Rule 1: Emergency override expedites near-due orders.
- Rule 2: Low-stock rebalance prevents downstream lateness.
- Rule 3: LLM selects structured JSON action when no critical override is needed.

Key implementation details:
- OpenAI client with injected environment credentials.
- One-time proxy warmup call to ensure observable LLM traffic.
- Retry logic for transient model/API failures.
- Strict schema validation and safe action normalization.
- Route candidate ranking weighted toward lead time for delivery reliability.

## Architecture

- `env.py`: Environment dynamics and reward shaping.
- `server.py`: FastAPI endpoints (`/reset`, `/step`, `/state`, `/grade`).
- `models.py`: Pydantic models (`Observation`, `Action`, `Reward`, `StepResult`).
- `graders.py`: Deterministic task graders.
- `inference.py`: Hackathon inference runner with strict structured logs.
- `openenv.yaml`: OpenEnv metadata and task specs.

## Tasks And Evaluation

Tasks:
- steady_state (easy)
- port_strike (medium)
- black_swan (hard)

Latest evaluation snapshot is available in `results.md`.

From current results:
- Average score across all runs: 0.6586
- Best per task:
- steady_state: 0.7452
- port_strike: 1.0000
- black_swan: 0.4109

## Compliance Notes (Important)

For hackathon deep validation:
- Use injected environment variables for LLM calls.
- Do not hardcode private credentials.
- Do not bypass the provided proxy endpoint.

Inference runner requirements satisfied:
- Script name is `inference.py` at project root.
- Structured stdout logs follow [START], [STEP], [END] format.
- OpenAI client is used for model calls.

Required runtime variables:
- `API_BASE_URL`
- `MODEL_NAME`
- `HF_TOKEN` (or compatible injected key path)

Recommended defaults:
- `MODEL_NAME=Qwen/Qwen2.5-3B-Instruct` (cost-aware baseline)

## Local Run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start API server:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

3. Run inference:

```bash
export API_BASE_URL="http://127.0.0.1:8000"
export MODEL_NAME="Qwen/Qwen2.5-3B-Instruct"
export HF_TOKEN="your-token"
python inference.py
```

Expected structured log shape:

```text
[START] task=steady_state env=supply-chain-chaos model=Qwen/Qwen2.5-3B-Instruct
[STEP] step=1 action=... reward=... done=false error=null
[END] success=true steps=... rewards=...
```

## Reproducibility

- Default seed is fixed in environment presets.
- Graders are deterministic.
- Task presets and endpoint contracts are versioned in code.

## License And Usage

This repository is intended for hackathon submission, reproducible evaluation, and educational demonstration of robust agent design for logistics operations.
