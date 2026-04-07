# Fixes Applied

Project: Supply Chain Chaos
Date: 2026-04-06

## Purpose

This changelog captures the practical fixes that aligned runtime behavior, benchmarks, and submission documentation.

## Core Runtime Fixes

1. Default backend switched to Hugging Face
- Changed default `SUPPLY_CHAIN_AGENT_BACKEND` from `dummy` to `huggingface` in inference flow.

2. Startup model proof line added
- Added one-time startup log:
  - `[INFO] backend=huggingface model=google/flan-t5-small loaded=True`
- This removes ambiguity about whether the local Hugging Face path is active.

3. Startup model label corrected
- Ensured START log reflects active backend model label instead of stale values.

## Evaluation and Reporting Fixes

4. Grader score included in benchmark rows
- Updated evaluation pipeline so each run also records normalized `score`.
- CSV schema now includes: `backend, task, score, ...`.

5. Markdown report expanded
- Results generator now summarizes average score plus reward metrics.
- Added run matrix table for direct per-run comparison.

6. Benchmark artifacts regenerated
- Updated `evaluation_results.csv` with current six-run matrix.
- Updated `results.md` with narrative summary and run table.

## Documentation Alignment Fixes

7. README aligned to current demo path
- Hugging Face is documented as default demo backend.
- Dummy is explicitly baseline/fallback.
- Reproducibility note for default seed `42` is included.

8. Submission checklist simplified and aligned
- Replaced stale checklist with concise, current validation list.
- Added direct references to benchmark artifacts.

9. Legacy docs refreshed
- Rewrote `COMPLIANCE_REPORT.md`, `SUBMISSION_GUIDE.md`, and this file to remove outdated env naming and old backend guidance.

10. Mirrored Space docs synchronized
- Applied same legacy-doc cleanup in `supply-chain-chaos-space` copies.

## Outcome

- Demo behavior, validation docs, and benchmark artifacts now use one consistent story.
- The submission package emphasizes reproducibility, deterministic grading, and transparent evidence.