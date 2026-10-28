# Knowledge graph-constrained LLM agent for automated FE modeling of girder bridges: research materials

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23433648.svg)](https://doi.org/10.5281/zenodo.23433648)

Archived on Zenodo; DOI for all versions: 10.5281/zenodo.23433648 (resolves to the latest version). The version cited in the manuscript is v0.2.5-review; its version-specific DOI is listed on the Zenodo record.

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

## Offline re-validation under the stricter validator

`analysis/strict_revalidation.py` re-submits the final accepted decisions of all 90 C5 runs (3414 decisions, recorded values, units and evidence, final instances) to the evaluated validator (control) and to the stricter variant, without LLM calls:

```
python analysis/strict_revalidation.py evaluated OUT
python analysis/strict_revalidation.py strict OUT
```

Results are in `review_evidence/strict_revalidation/`: the evaluated validator re-accepts all decisions; the stricter variant accepts 3312 and rejects 102 (37 runs), all for the granularity of supporting input citations. No decision value changes.

## Run dates

`review_evidence/run_timestamps.json` lists the file modification times (UTC+8) of all original session records. All experiments ran on 27-28 September 2026. These are file timestamps, not service-side request records.

## Non-LLM rule baseline (R)

`analysis/rule_parser.py` is a fixed-schema parser for the four-part structured description (English and Chinese), written from the published input format; it reads no reference answers and was frozen before evaluation (SHA-256 recorded in `analysis/run_rule_baseline.py`). `analysis/run_rule_baseline.py` parses each input, writes the instance, completes all decisions deterministically from the governing KG nodes (same selector as the deterministic replay), generates the model, and only then evaluates it against the reference:

```
python analysis/run_rule_baseline.py
```

Results (`analysis/rule_baseline_results.json`, sessions in `analysis/rule_baseline/`): 30/30 structured main problems, 3/3 long units, 3/3 structured Chinese inputs, 0/18 free-text inputs (all rejected as out of schema), 5/6 boundary inputs refused (schema mismatches), 6/6 unmodified problems correct without false alarms. No LLM calls.

