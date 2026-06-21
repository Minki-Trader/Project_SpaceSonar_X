# Features

Reusable feature logic for the ONNX lab.

Rules:

- Features must be right-aligned to closed bars.
- Feature order must be represented by schema and hash before ONNX export.
- There is no default feature set. Each feature surface starts as an experiment-local definition until evidence promotes it.
- Auxiliary-symbol features require local MT5 live-chart evidence, an explicit merge policy, and a feature schema before model or runtime use.

Current helpers:

- `session_calendar.py`: broker-clock timestamp handling and US session features.
