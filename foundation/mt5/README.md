# MT5

EA sources, include modules, and `.set` templates for ONNX runtime probes.

Preferred layout:

- entry `.mq5` files stay thin
- reusable modules live under `include/`
- `.set` templates live under `set_templates/`
- bundle identity is verified by manifest and hash, not by file name alone

MT5 attempt source of truth:

- `runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml`

Runtime learning probes are normal evidence for runtime questions. Do not skip them only because proxy results are weak, trade count is low, the candidate is ambiguous, setup might fail, or the probe is heavy.
