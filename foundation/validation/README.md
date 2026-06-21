# Validation

Reusable validation, WFO, selection-bias, and risk checks.

Completed execution is not a meaningful result without measurement identity and judgment boundary.

Control-plane preflight validators:

- `control_plane_validator.py`: parses control YAML/JSON/CSV, checks receipt/provenance/branch/agent-allocation templates, and runs import smoke.
- `routing_smoke_eval.py`: checks the 12-20 prompt routing smoke fixture against `docs/agent_control/work_family_registry.yaml`.
