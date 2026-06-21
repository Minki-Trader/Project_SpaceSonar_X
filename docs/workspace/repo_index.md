# SpaceSonar X Repo Index

Purpose: make GitHub, Codex, and GPT connector entry deterministic.

Read order:

1. `AGENTS.md`
2. `README.md`
3. `docs/workspace/workspace_state.yaml`
4. `docs/workspace/lab_profile.yaml`
5. `docs/agent_control/work_family_registry.yaml` only for non-trivial routing
6. `docs/contracts/onnx_lab_contract.yaml` only for ONNX bundle/schema/export work
7. `foundation/config/mt5_runtime_probe_contract.yaml` only for MT5/runtime claims

Project identity:

- name: Project SpaceSonar X
- mode: ID-based blank-slate ONNX lab
- primary instrument: FPMarkets US100
- timeframe: M5
- current claim boundary: planning scaffold and research lab, not selected baseline or runtime authority

Important roots:

- `src/spacesonar/`: reusable Python package surface
- `foundation/`: collectors, feature/label/training/ONNX/parity/MT5 reusable logic
- `configs/`: recipe specs and MT5 profile templates
- `lab/`: hypotheses, campaigns, runs, candidates, templates, and evidence receipts
- `runtime/`: ONNX/EA bundle packages and MT5 attempt records
- `docs/`: workspace truth, policies, contracts, registers, and agent control
- `.agents/skills/`: project-specific Codex skills

Storage rules:

- durable identity uses repo-relative paths
- one run lives in `lab/runs/<run_id>/`
- one bundle lives in `runtime/packages/<bundle_id>/`
- one MT5 attempt lives in `runtime/mt5_attempts/<attempt_id>/`
- registries under `docs/registers/` are compact indexes, not proof by themselves

Forbidden inherited defaults:

- no default feature count
- no default feature recipe mix
- no default label
- no default prediction target
- no default direction mapping
- no default holding period
- no default model family
- no default output head
- no default decision threshold
- no selected baseline
- no runtime authority

Runtime rule:

Runtime behavior, Strategy Tester output, EA/ONNX handoff, economics, runtime authority, live readiness, and handoff-complete claims require matching MT5 runtime evidence. Proxy or ONNX smoke evidence cannot replace it.

