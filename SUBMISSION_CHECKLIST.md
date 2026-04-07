"""
META HACKATHON SUBMISSION CHECKLIST
Supply Chain Chaos Environment

Current status: aligned with the Hugging Face-first demo path.
"""

# PRE-SUBMISSION CHECKLIST

## Phase 1: Required Validation

- [x] FastAPI server starts locally on port 8000
- [x] `GET /reset` returns a valid observation
- [x] `POST /step` accepts `Action` and returns a step result
- [x] `GET /state` returns the current observation
- [x] `GET /grade?task=<task_name>` returns a numeric score
- [x] `openenv.yaml` exists and describes the environment
- [x] `docker build` succeeds locally
- [x] `inference.py` runs end-to-end without errors

## Demo Path

- [x] Default backend is `huggingface`
- [x] Default model is `google/flan-t5-small`
- [x] `dummy` remains available as a deterministic fallback/baseline
- [x] Run output includes `[START]`, `[INFO]`, `[STEP]`, and `[END]`
- [x] Demo run completes with `success=true`
- [x] The same environment preset uses the same default seed (`42`)

## Environment Variables

- [x] `API_BASE_URL` is configurable
- [x] `SUPPLY_CHAIN_AGENT_BACKEND` is configurable and defaults to `huggingface`
- [x] `SUPPLY_CHAIN_HF_MODEL` is configurable and defaults to `google/flan-t5-small`
- [x] `HF_TOKEN` is configurable for Hugging Face downloads

## Evidence Collected

- [x] [results.md](results.md) contains the benchmark summary
- [x] `evaluation_results.csv` contains backend/task comparison data
- [x] The Hugging Face startup line is visible in the demo output: `[INFO] backend=huggingface model=google/flan-t5-small loaded=True`

## Benchmark Snapshot

| backend | task | score | delivered | late | final reward | total reward | steps | done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dummy | steady_state | 0.5203 | 3 | 0 | 172.94 | 110.17 | 4 | True |
| dummy | port_strike | 0.9018 | 4 | 0 | 224.46 | 365.01 | 6 | True |
| dummy | black_swan | 0.3732 | 2 | 0 | 85.57 | 98.15 | 5 | True |
| huggingface | steady_state | 0.7452 | 3 | 0 | 182.59 | 222.61 | 4 | True |
| huggingface | port_strike | 1.0000 | 4 | 0 | 226.46 | 737.72 | 8 | True |
| huggingface | black_swan | 0.4109 | 2 | 0 | 0.00 | 135.89 | 20 | False |

## Final Submission Package

- [x] `inference.py`
- [x] `server.py`
- [x] `env.py`
- [x] `models.py`
- [x] `graders.py`
- [x] `requirements.txt`
- [x] `Dockerfile`
- [x] `README.md`
- [x] `results.md`
- [x] `evaluation_results.csv`

## Notes

- The environment is graph-based, and the grader evaluates environment state/trajectory quality, not prompt text.
- The Hugging Face model is local and reproducible; the dummy backend is deterministic fallback only.
- Use the same task preset and seed (`42`) when comparing runs.
