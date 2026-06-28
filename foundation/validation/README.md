# Validation

Reusable validation, WFO, selection-bias, and risk checks.

Completed execution is not a meaningful result without measurement identity and judgment boundary.

Control-plane preflight validators:

- `control_plane_validator.py`: parses control YAML/JSON/CSV, checks receipt/provenance/branch/agent-allocation templates, and runs import smoke.
- `writer_scope_evidence_smoke.py`: validates only the touched run/campaign evidence surface: run manifest, experiment receipt, artifact lineage, metrics, optional run refs, optional campaign proxy summary, claim boundary, and hash refs. This is the default no-pytest run-evidence smoke.
- `machine_yaml_identity_lint.py`: validates touched machine YAML records do not contain PyYAML alias/anchor identity tokens such as `&id001` or `*id001`.
- `routing_smoke_eval.py`: checks the 12-20 prompt routing smoke fixture against `docs/agent_control/work_family_registry.yaml`.
- `refresh_artifact_registry_hashes.py`: refreshes registry sha256/size identity for existing repo-relative artifacts after checkout or line-ending drift; use `--path` for touched-row scope during ordinary writer work.

Default operation must not call `pytest`, `python -m spacesonar.cli project validate`, full active-record validation, broad hash resync, or full control-plane validation for ordinary run writing or progress checks. Use the writer-scope smoke, touched parse/compile/import checks, touched YAML identity lint, routing/policy lint, or projection checks first; escalate only at campaign/wave boundaries, protected claim changes, shared validator/contract semantics changes, explicit user request, or source-of-truth drift.

The default stability contract is `docs/agent_control/writer_scope_operating_contract.yaml`.
Validation tools confirm writer-owned records; they do not replace the writer's
manifest, receipt, summary, hash, availability, claim-boundary, and next-action
fields. Broad validation commands require the operational command-intent gate
before execution.
