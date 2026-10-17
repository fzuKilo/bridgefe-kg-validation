# Historical records and recoverability

review_evidence/run_inventory.json maps completed summary rows to archived session files with SHA256 hashes, preserves program-error line numbers and records duplicate selection. C5 rows point to their recorded source directories and are shared observations, not new independent replications. Hashes attest the present sanitized files, not their historical creation time. File modification times and seed values are not request dates.

Historical provider response identities, request timestamps, commands, sampling/retry settings, original source commit and dependency lock were not retained or authenticated. Current source defaults are inspectable, but cannot fill these fields. The two archived model-group labels remain unauthenticated. No claim of exact historical API replay is made.

version_map.json distinguishes the stricter validator variant, the evaluated validator used by the deterministic replay, and unknown original historical versions. Archived outcomes are preserved. Revised scripted checks are implementation evidence, not new LLM experiments.
