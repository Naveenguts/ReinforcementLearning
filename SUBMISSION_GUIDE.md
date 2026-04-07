# Submission Guide

Project: Supply Chain Chaos
Date: 2026-04-06

## Goal

Submit a reproducible, judge-friendly package where the environment is the evaluated object and evidence is easy to verify.

## Mandatory Files

- `inference.py`
- `server.py`
- `env.py`
- `models.py`
- `graders.py`
- `openenv.yaml`
- `requirements.txt`
- `Dockerfile`
- `README.md`

## Strongly Recommended Evidence

- `SUBMISSION_CHECKLIST.md`
- `COMPLIANCE_REPORT.md`
- `FIXES_APPLIED.md`
- `evaluation_results.csv`
- `results.md`

## Demo Defaults

- Backend default: `huggingface`
- Hugging Face model default: `google/flan-t5-small`
- Fallback/baseline backend: `dummy`
- Default reproducibility seed in environment: `42`

## Environment Variables

Required:

- `API_BASE_URL`

Optional:

- `SUPPLY_CHAIN_AGENT_BACKEND` (`huggingface` or `dummy`)
- `SUPPLY_CHAIN_HF_MODEL` (default `google/flan-t5-small`)
- `HF_TOKEN` (for model download/auth)
- `SUPPLY_CHAIN_TASK`
- `SUPPLY_CHAIN_MAX_STEPS`

## Local Validation Flow

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start API server:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

3. Run default demo:

```bash
export API_BASE_URL="http://127.0.0.1:8000"
export SUPPLY_CHAIN_AGENT_BACKEND="huggingface"
export SUPPLY_CHAIN_HF_MODEL="google/flan-t5-small"
export HF_TOKEN="your-token"
python inference.py
```

Expected run markers:

- `[START] task=... env=supply-chain-chaos model=google/flan-t5-small`
- `[INFO] backend=huggingface model=google/flan-t5-small loaded=True`
- `[STEP] ...`
- `[END] success=...`

4. Generate benchmark report (if needed):

```bash
python evaluate.py
python generate_results_md.py
```

## Final Pre-Submit Checks

- API endpoints respond: `/reset`, `/step`, `/state`, `/grade`
- Inference run emits START/INFO/STEP/END lines
- `results.md` and `evaluation_results.csv` are present and current
- Docker image builds successfully
- Docs are consistent with Hugging Face-first defaults

## What Reviewers Should See Quickly

- The environment is graph-based and deterministic in evaluation setup.
- Grading is normalized and task-aware.
- Hugging Face path is active and visible in logs.
- Dummy backend is available for deterministic baseline comparisons.
- Reproducibility is supported via stable seed and fixed task presets.