# Parity

Python, ONNX, and MT5 parity helpers and fixtures.

Parity preflight is not runtime authority. Runtime claims require MT5 probe evidence.

Runtime evidence levels:

- `L0_contract_declared`: task, feature, label, schema, split, and decision contract is declared.
- `L1_python_onnx_parity`: Python and ONNX agree on fixture inputs.
- `L2_label_outcome_parity`: labels/outcomes are reproducible under the declared contract.
- `L3_mt5_micro_probe`: MT5 can execute a narrow runtime observation.
- `L4_split_runtime_probe`: required split-period MT5 reports exist for research runtime observation.
- `L5_candidate_runtime_evidence`: candidate-specific runtime evidence exists with matching manifests.

Rules:

- Every valid proxy/model-bearing run must progress to `L4_split_runtime_probe`; proxy-only closeout is not an allowed endpoint.
- If L4 remains promising, the next runtime path is `L5_candidate_runtime_evidence`.
- A proposed proxy surface that cannot be materialized into ONNX/EA/MT5 execution must be repaired before it counts as proxy evidence.
- Parity is tracked for every campaign, not only after candidate selection. Each campaign must record how proxy assumptions map to MT5 runtime behavior before closing proxy evidence.
- Proxy-vs-runtime divergence is an experiment result. Record whether the case is proxy_good_runtime_good, proxy_good_runtime_bad, proxy_bad_runtime_bad, proxy_bad_runtime_good, or invalid_or_unmaterializable.
- A proxy-bad/runtime-good surprise must be preserved as a clue or new hypothesis. A proxy-good/runtime-bad mismatch must be treated as interpretation or execution drift until explained.
- Parity reconciliation requires at least one explicit repair, conversion, or interpretation attempt. It does not require forcing proxy and MT5 into equality when the true semantics differ.
- Unit semantics are part of parity: point, pip, tick size, digits, price distance, ATR multiplier, lot step, rounding, and execution timing must be recorded when they affect the translation.
- ONNX smoke does not imply MT5 execution.
- Python-vs-ONNX parity does not imply Strategy Tester economics.
- MT5 compile does not imply tester output.
- Every runtime-facing surface must record `runtime_learning_probe_decision`.
- Runtime claims require `foundation/config/mt5_runtime_probe_contract.yaml` plus the named period and execution profiles.

Minimum `proxy_runtime_parity` fields:

- `shared_contract`
- `proxy_assumptions`
- `runtime_assumptions`
- `known_differences`
- `interpretation_drift_risks`
- `minimum_reconciliation_attempt`
- `unit_semantics`
- `comparison_class`
- `divergence_judgment`
- `prevention_memory`
- `follow_up_action`
- `claim_boundary`
