# Validator versions

Two validator implementations are included.

- **Evaluated implementation** (`supplementary/replay_20261017/validator_evaluated.py`): used for all LLM results reported in the manuscript and for the frozen-input deterministic replay. Within a priority class the first applicable node in graph order is used; citing an applicable governing node is sufficient; input-override citations are checked for the existence of the cited field.
- **Stricter variant** (`kgfem/`): binds override citations to the slot context, requires the selected governing source, rejects tied highest-priority sources, saves source/input/snapshot metadata, marks withdrawn nodes inactive, and invalidates modal facts on structural revision or instance writes. Regression: 33/33 benchmark cases agree with the references. These are implementation checks, not new LLM experiments or independent engineering validation.

Licensing: see LICENSES.md; third-party standards content is excluded.
