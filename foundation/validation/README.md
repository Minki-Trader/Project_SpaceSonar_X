# Validation

Reusable validation, WFO, selection-bias, and risk checks.

Completed execution is not a meaningful result without measurement identity and judgment boundary.

Control-plane preflight validators:

- `control_plane_validator.py`: parses control YAML/JSON/CSV, checks receipt/provenance/branch/agent-allocation templates, and runs import smoke.
- `writer_scope_evidence_smoke.py`: validates only the touched run/campaign evidence surface: run manifest, experiment receipt, artifact lineage, metrics, optional run refs, optional campaign proxy summary, claim boundary, and hash refs. This is the default no-pytest run-evidence smoke.
- `machine_yaml_identity_lint.py`: validates touched machine YAML records do not contain PyYAML alias/anchor identity tokens such as `&id001` or `*id001`.
- `writer_scope_contract_lint.py`: reuses `src/spacesonar/control_plane/writer_contract.py` to confirm touched writer-owned YAML/JSON records contain `writer_preflight_gate`, `validation_attempt_budget`, writer-scope fields, and the two-pass validation budget before they become operating proof.
- `routing_smoke_eval.py`: checks the 12-20 prompt routing smoke fixture against `docs/agent_control/work_family_registry.yaml`.
- `operational_stability_lint.py`: checks that AGENTS, routing, skills, writer-scope contract, CI, and validation docs all enforce the no-pytest writer-first operating loop.
- `claim_vocabulary.yaml`: must stay ASCII machine-token-only and structurally complete for protected claim boundaries; mojibake or missing canonical protected tokens are operating-policy drift.
- `refresh_artifact_registry_hashes.py`: refreshes registry sha256/size identity for existing repo-relative artifacts after checkout or line-ending drift; use `--path` for touched-row scope during ordinary writer work.

Default operation must not call `pytest`, `python -m spacesonar.cli project validate`, full active-record validation, broad hash resync, or full control-plane validation for ordinary run writing or progress checks. Use the writer-scope smoke, touched parse/compile/import checks, touched YAML identity lint, routing/policy lint, or projection checks first; escalate only at campaign/wave boundaries, protected claim changes, shared validator/contract semantics changes, explicit user request, or source-of-truth drift.

The default stability contract is `docs/agent_control/writer_scope_operating_contract.yaml`.
Validation tools confirm writer-owned records; they do not replace the writer's
manifest, receipt, summary, hash, availability, claim-boundary, and next-action
fields. Broad validation commands require the operational command-intent gate
before execution. The manual `full-regression` workflow must collect the same
gate fields before pytest can run.

Writer-scope validation has a hard default budget of two passes: initial smoke
after write, then one owner repair plus the same scoped smoke. A third pass must
stop into a blocker/reopen condition or a recorded command-intent escalation; it
must not become another routine validation loop.

For strict writer-owned YAML surfaces, the preferred stability mechanism is the
write-time guard in `src/spacesonar/control_plane/writer_contract.py`, called by
`ControlPlaneTransaction.stage_yaml`. Missing or pending contract fields fail
before mutation; lint is for drift detection, not for making a bad record valid.
