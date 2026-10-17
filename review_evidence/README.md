# Verification evidence

Prepared 2026-10-17. This folder contains the evidence used to check the run records, statistics, replay and benchmark references reported in the manuscript.

- run_inventory.json: summary-to-session mapping, exclusions, duplicate selection, present-file hashes.
- version_map.json: separation of historical results, frozen-input replay and current revision.
- historical_configuration.json: missing facts, never filled using current defaults.
- execution_environment.json and requirements-audit.txt: current audit environment.
- executed/: actual new offline provenance and 33-case reference checks.

Reproduce from package root using Python 3.12: `python analysis/verify_revision.py`, `python analysis/reanalyse.py`, `python analysis/run_control.py --phase pilot`, `python analysis/run_control.py --phase full`, `python analysis/summarize_control.py`. Outputs are checks of the supplied artifacts; no paid model calls. The replay pins the evaluated validator before imports.

CITATION.cff supplies citation metadata. Licensing is described in LICENSES.md.
