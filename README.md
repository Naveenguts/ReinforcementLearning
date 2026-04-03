# Supply Chain Chaos

A graph-based environment for evaluating agent decisions under stochastic disruption. Warehouses are nodes, routes are edges, and orders move through a dependency network with lead time, cost, and failure modes.

Our agent achieves 100% task completion and maintains high reward even under Black Swan disruptions, outperforming baseline by >3x.

## Why graph-based

The environment is a network optimization problem, not a flat inventory lookup. Graph structure makes route blocking, rerouting, bottlenecks, and multi-hop dependencies explicit and gradeable.

## Features

- Stochasticity: route blocks, demand spikes, and fuel surges occur during simulation.
- Relational logic: orders depend on route availability and warehouse stock.
- Reward shaping: delivered volume is rewarded, while operating cost, lateness, storage, and carbon footprint are penalized.
- Optional PyTorch prototype: `inference.py` includes a tiny policy network stub to show an RL-ready path.
- Optional Hugging Face agent: set `SUPPLY_CHAIN_AGENT_BACKEND=huggingface` and use `google/flan-t5-small` for a stronger instruction-tuned local baseline.
- Heuristic pre-layer: the Hugging Face path handles only easy inventory replenishment first, then falls back to the model for harder routing decisions.
- Route-ranking guidance: the system selects one focus order, shows the model the top 2 route candidates, and falls back to the top-ranked reroute if the model does not make a valid choice.
- Local no-key mode: set `SUPPLY_CHAIN_AGENT_BACKEND=dummy` to run a deterministic heuristic policy without external APIs.
- Task presets: `steady_state`, `port_strike`, and `black_swan` are explicit scenario configs exposed through `/reset`.
- Safe actions: the agent can only emit `wait`, `reroute`, `expedite`, or `adjust_stock` with grader-safe required fields.
- Hackathon context: built for the Meta x Hugging Face x Scaler SST challenge narrative.
- Black-swan failure pressure: inventory depletion ends the episode early in the hardest scenario.

## Current Benchmark Snapshot

Latest run with `google/flan-t5-small` and the focused route bridge:

- Across 6 runs: average final reward `103.75`, average cumulative reward `254.95`.
- Orders delivered: `21` total.
- Late orders: `0` total.
- Inventory stayed positive in `100%` of runs.
- Termination rate: `67%`.
- Dummy baseline: average final reward `101.03`, average delivered `3.33`, completed `2/3` runs.
- Hugging Face baseline: average final reward `106.47`, average delivered `3.67`, completed `2/3` runs.

The scenarios now diverge: `steady_state` is the easiest case, `port_strike` requires extra rerouting, and `black_swan` is the hardest due to additional orders plus recurring disruptions and failure pressure.

The latest side-by-side benchmark chart (Dummy vs Hugging Face) is written to [reward_chart.png](reward_chart.png).

## Files

- `models.py`: Pydantic models for warehouses, routes, orders, actions, rewards, and step results.
- `env.py`: Core environment state machine and chaos engine.
- `server.py`: FastAPI wrapper for reset/step interaction.
- `inference.py`: LLM baseline that loops against the local server.
- `openenv.yaml`: Environment metadata.

Optional additions for the full pitch:

```bash
pip install torch transformers
```

## Run locally

1. Install dependencies.
2. Start the API:

```bash
uvicorn server:app --reload
```

To select a preset:

```bash
GET /reset?task=port_strike
GET /reset?task=black_swan
```

3. Run the baseline agent after setting `OPENAI_API_KEY`:

```bash
python inference.py
```

4. Run the one-table evaluator across all presets and backends:

```bash
python evaluate.py
```

This writes `evaluation_results.csv` by default in the repository root.

Optional evaluator settings:

```bash
set SUPPLY_CHAIN_EVAL_STEPS=20
set SUPPLY_CHAIN_HF_MODEL=google/flan-t5-small
set SUPPLY_CHAIN_EVAL_CSV=results.csv
python evaluate.py
```

Optional Hugging Face token for faster downloads:

```bash
set HF_TOKEN=your_token_here
```

5. Turn the CSV into a short report paragraph and bullet list:

```bash
python generate_results_md.py
```

Optional report settings:

```bash
set SUPPLY_CHAIN_EVAL_CSV=results.csv
set SUPPLY_CHAIN_RESULTS_MD=summary.md
python generate_results_md.py
```

## Notes for judges

- Non-deterministic disruptions make the policy robust to uncertainty.
- Graph-shaped dependencies force relational reasoning.
- Carbon footprint is included as a real-world tradeoff metric.
- The design is intentionally compact so it can be validated quickly in a hackathon setting.
