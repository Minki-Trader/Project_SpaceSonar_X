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

- ONNX smoke does not imply MT5 execution.
- Python-vs-ONNX parity does not imply Strategy Tester economics.
- MT5 compile does not imply tester output.
- Every runtime-facing surface must record `runtime_learning_probe_decision`.
- Runtime claims require `foundation/config/mt5_runtime_probe_contract.yaml` plus the named period and execution profiles.
