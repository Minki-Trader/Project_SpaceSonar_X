---
name: spacesonar-environment-reproducibility
description: Capture environment, command, dependency, path, and regeneration identity for reproducible ONNX lab work.
---

# SpaceSonar Environment Reproducibility

Use this skill when work creates or depends on generated data, models, ONNX bundles, runtime packages, reports, or verification commands.

## Required Output

- `command`
- `cwd`
- `python_or_tool_version`
- `dependency_summary`
- `env_vars_relevant`
- `input_paths`
- `output_paths`
- `regeneration_command`
- `reproducibility_boundary`

## Guardrails

- Do not store local absolute terminal paths as durable identity.
- Use repo-relative paths plus hashes and ids.
- For generated artifacts, prefer manifest plus regeneration command over committing heavy files.
- On Windows deep paths, discover with repo-relative `rg --files` before declaring evidence missing.

