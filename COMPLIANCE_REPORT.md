# Final Compliance Report

Project: Supply Chain Chaos
Date: 2026-04-06
Status: Submission-ready for Phase 1 style validation checks

## Scope

This report confirms alignment between implementation, demo flow, and judge-facing documentation.

## Compliance Highlights

- OpenEnv-compatible API is present and documented: `/reset`, `/step`, `/state`, `/grade`.
- Deterministic grading exists and returns normalized scores in `[0.0, 1.0]`.
- Three task presets are available: `steady_state`, `port_strike`, `black_swan`.
- Typed request and response models are used across the environment API.
- Dockerized deployment path is available with documented run commands.

## Current Demo Path

- Default backend: `huggingface`
- Default model: `google/flan-t5-small`
- Deterministic fallback baseline: `dummy`
- Reproducibility default: seed `42`

The demo run now emits:

- `[START] ... model=google/flan-t5-small`
- `[INFO] backend=huggingface model=google/flan-t5-small loaded=True`
- `[STEP] ...`
- `[END] ...`

This provides explicit proof that the Hugging Face model path is active.

## Evidence Artifacts

- `evaluation_results.csv`: backend/task matrix with `score`, rewards, delivery stats, and completion flag.
- `results.md`: human-readable benchmark summary plus run matrix.
- `README.md`: judge-facing narrative and instructions aligned with the current backend defaults.
- `SUBMISSION_CHECKLIST.md`: final checklist aligned with current behavior and artifacts.

## Benchmark Snapshot

| backend | task | score | delivered | late | final reward | total reward | steps | done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dummy | steady_state | 0.5203 | 3 | 0 | 172.94 | 110.17 | 4 | True |
| dummy | port_strike | 0.9018 | 4 | 0 | 224.46 | 365.01 | 6 | True |
| dummy | black_swan | 0.3732 | 2 | 0 | 85.57 | 98.15 | 5 | True |
| huggingface | steady_state | 0.7452 | 3 | 0 | 182.59 | 222.61 | 4 | True |
| huggingface | port_strike | 1.0000 | 4 | 0 | 226.46 | 737.72 | 8 | True |
| huggingface | black_swan | 0.4109 | 2 | 0 | 0.00 | 135.89 | 20 | False |

## Final Assessment

- Documentation and execution path are now consistent.
- Legacy references to old model env naming were removed from core submission docs.
- The package contains reproducible, inspectable evidence for judge review.

## Residual Notes

- `black_swan` remains the hardest scenario and can hit max steps before termination, which is expected and visible in the benchmark table.
- Use the same task preset and seed `42` when comparing policy changes.