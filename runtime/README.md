# Runtime

Runtime package and MT5 attempt workspace.

- `runtime/packages/<bundle_id>/`: ONNX/EA handoff packages, manifests, schemas, hashes, parity reports, and generated files.
- `runtime/mt5_attempts/<attempt_id>/`: Strategy Tester attempt manifests, reports, telemetry, parsed metrics, and contract audits.

Generated package payloads are ignored by default. Keep durable identity in manifests and registers.

Source of truth:

- bundle: `runtime/packages/<bundle_id>/experiment_bundle.json`
- MT5 attempt: `runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml`

Registry rows point to these records. They do not replace them.
