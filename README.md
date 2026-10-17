# Executable knowledge validation for bridge FE modeling

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23433649.svg)](https://doi.org/10.5281/zenodo.23433649)

Archived version: Zenodo DOI 10.5281/zenodo.23433649 (v0.2.1-review); all versions: 10.5281/zenodo.23433648.

Research materials published on GitHub 2026-10-17: https://github.com/fzuKilo/bridgefe-kg-validation. Code: MIT; data and documentation: CC BY 4.0; design-code provision excerpts excluded (see LICENSES.md).

Research prototype for straight planar linear-elastic girder bridges: natural-language instance extraction, executable KG, decision validation, deterministic OpenSeesPy generation and diagnostic feedback. Not engineering design certification.

## Contents

- kgfem/: implementation and evaluation tools.
- bridgefe_bench/: 33 inputs, reference decisions/responses and reference-generation code. No original standard PDFs or drawings.
- runs_*/: archived result summaries, including recorded program-error rows, and sessions for completed jobs. C5 uses original relative source directories.
- analysis/: portable statistics and frozen-initial-instance replay scripts.
- results/: existing audit, replay, convergence and override evidence.
- docs/: prompts, environment, provenance and preparation checks.

The authors confirmed on 2026-10-16 that reference answers were reviewed by two bridge engineers. docs/legacy/ preserves older notes, including superseded pending-review statements.

## Offline use

Use Python 3.12 and a virtual environment; install requirements.txt. OpenSeesPy availability is platform-dependent. docs/environment_current.json describes preparation versions, not a verified historical lock.

From this directory:

```sh
python -m kgfem.cli run --backend scripted --problems A01 B03 C06 --out local_runs/smoke
python analysis/verify_revision.py
python analysis/reanalyse.py
python analysis/run_control.py --phase pilot
python analysis/run_control.py --phase full
python analysis/summarize_control.py
```

The replay uses each historical first write_instance argument, not the final corrected instance or a fixed-format parser. References are read after completion for scoring. It locks input while the historical LLM workflow permits correction, so it is not an equal-permission new experiment: 84/90 deterministic versus 89/90 historical; among 85 unchanged initial instances both score 84/85.

## Optional model backends

Keys are read from environment variables; none are distributed. New calls incur service usage. Choose and log actual service/model identifiers instead of trusting legacy model examples. Historical request/response model IDs, exact sampling, absolute times and billing were not retained. C0/C1 have a separate direct-model argument; archived cross-configuration model identity cannot be certified.

## Limits

KG and references share provisions/idealizations; consistency is not physical validation. Internally consistent input errors can pass. The archived validator allowed cross-support Ge citations and left withdrawn graph nodes insufficiently marked. The revised validator fixes these defects; historical performance is not reattributed to the revised implementation. Repetitions are clustered and shared C5 observations are not independent replications.

Local paths in staging JSON are replaced with ${PROJECT_ROOT}; relative source fields remain. Not all intermediate generated scripts/IR/graphs are included. Read RELEASE_REVIEW.md before publication. Repository: https://github.com/fzuKilo/bridgefe-kg-validation. Licensing is described in LICENSES.md.

## Verification evidence

Read review_evidence/README.md and docs/HISTORICAL_RECORDS.md. The deterministic replay explicitly loads the evaluated validator (`supplementary/replay_20261017/validator_evaluated.py`); regression checks of the stricter variant in `kgfem/` run separately. Repository: https://github.com/fzuKilo/bridgefe-kg-validation.

## Random seeds

All bootstrap resampling in the analysis scripts uses the seed 20261016 (`kgfem/summarize.py`, `analysis/reanalyse.py`, `analysis/audit_clusters.py`, `analysis/summarize_control.py`, `supplementary/replay_20261017/prepare_evidence.py`). The constant `SEED = 20260925` in `bridgefe_bench/src/problems.py` is the benchmark-generation seed; it defines the problems themselves and is not a statistical resampling seed.

## Backbone model

All configurations of the main, ablation, error-injection, robustness, and scalability experiments use DeepSeek-V4-Flash (API model `deepseek-flash`); the agent configurations C2–C5 run in non-thinking mode, and the single-call baselines C0/C1 run with thinking enabled. The backbone comparison uses gpt-6-luna.
