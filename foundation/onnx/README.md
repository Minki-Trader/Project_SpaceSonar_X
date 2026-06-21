# ONNX

Reusable ONNX export, schema, smoke-test, and bundle helpers.

Expected outputs:

- model export manifest
- input/output schema
- ONNX hash
- feature order hash
- task surface id
- label or target id when the model has one
- Python ONNX smoke report
- bundle manifest

Bundle source of truth:

- `runtime/packages/<bundle_id>/experiment_bundle.json`

Export, smoke, parser, parity, runtime probe, economics, and handoff claims are separate evidence levels.
