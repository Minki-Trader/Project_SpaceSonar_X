# ONNX Lab Operating Policy

This project runs as an ID-based ONNX development lab.

## Identity

Use:

`idea_id -> hypothesis_id -> surface_id -> sweep_id -> run_id -> artifact_id -> bundle_id -> candidate_id`

Do not use numbered legacy units as active ownership or evidence identity.

Every non-trivial item must name exactly one `primary_family` and exactly one `primary_skill`.
Support skills are used only when they change execution, evidence, validation, routing, or closeout.

## Storage And Naming

Use repo-relative paths for durable identity.
Absolute terminal paths are allowed only as local context or raw log content.

Source-of-truth locations:

- `lab/campaigns/<campaign_id>/campaign_manifest.yaml`
- `lab/hypotheses/<idea_id>.yaml` or `lab/hypotheses/<hypothesis_id>.yaml`
- `lab/surfaces/<surface_id>/surface_manifest.yaml`
- `lab/runs/<run_id>/run_manifest.json`
- `lab/runs/<run_id>/experiment_receipt.yaml`
- `lab/runs/<run_id>/artifact_lineage.json`
- `lab/runs/<run_id>/metrics.json`
- `lab/candidates/<candidate_id>/candidate_summary.yaml`
- `runtime/packages/<bundle_id>/experiment_bundle.json`
- `runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml`

Run-local supporting files stay under:

- `lab/runs/<run_id>/logs/`
- `lab/runs/<run_id>/reports/`
- `lab/runs/<run_id>/artifacts/`
- `lab/runs/<run_id>/mt5/`

`docs/registers/` contains compact indexes only. A registry row never replaces run-local evidence.

Heavy artifacts are not committed by default. Track them with repo-relative path or URI, sha256, size, producer command, regeneration command, and consumer identity when applicable.

Do not duplicate a source-of-truth artifact across locations. If a copy is necessary, record `source_of_truth` and `copy_reason`.

## Realtime Symbol Rule

- The primary research instrument remains `US100` closed `M5` bars.
- Broker-native MT5 symbols may be used as auxiliary research/development inputs only when the target FPMarkets terminal can select the symbol, update its chart in real time, and return current bars or ticks.
- `BTCUSD` or gold symbols are eligible only after local live-chart evidence exists for the exact broker symbol name.
- `VIX`, single-stock symbols such as `NVDA`, delayed feeds, offline data, or any non-updating chart source are forbidden for active research, features, model inputs, runtime bundles, and EA input contracts.
- Auxiliary-symbol runtime use requires an explicit symbol contract, merge policy, feature schema, EA input contract, and MT5 runtime probe evidence.

## Blank-Slate Research Rule

- There is no default feature set, label, prediction target, direction class, holding period, model family, output head, threshold, or risk logic.
- Deleted legacy concepts are unavailable as current defaults. Do not recreate them from memory.
- Early work should discover and compare problem shapes: input surface, target/label surface, decision use, horizon or holding logic, evaluation method, and runtime feasibility.
- A run can test any explicit task shape, but the result only applies to that declared task surface.
- Do not optimize inherited settings before the experiment has named what it is trying to predict, estimate, rank, classify, or decide.

## Research Bias

- Prefer runnable experiments over advisory loops once a hypothesis and executable surface exist.
- MT5 runtime probes are normal verification for runtime questions, not extraordinary spend.
- Cost, heaviness, weak proxy results, low trade count, or imbalance are not standalone reasons to skip a narrow sufficient runtime probe when runtime evidence is required.
- Failed hypotheses become `negative_memory`, `invalid_setup`, `blocked_retry`, or `inconclusive` records with salvage value and reopen conditions.

## Sweep Order

Default research flow:

1. Task-surface scout
2. Input/target/decision definition
3. Broad sweep
4. Extreme sweep
5. WFO narrowing when a repeated clue exists
6. ONNX export and parity preflight
7. Bundle materialization
8. MT5 runtime probe when the question or claim requires runtime evidence

Fine search starts only after broad/extreme sweeps show a repeated surface clue.

## Candidate Lifecycle

Allowed states:

- `idea_open`
- `scout_surface`
- `research_candidate`
- `probe_candidate`
- `advisory_queue`
- `preserved_clue`
- `negative_memory`
- `invalid_setup`
- `blocked_retry`

`research_candidate` means compute allocation. It is not a selected baseline.

`probe_candidate` means runtime observation target. It is not runtime authority.

`advisory_queue` means waiting for Codex/Task Force advice. It is not reviewed, verified, pass, or selected.

## Stop Conditions

Stop, narrow, repair, or lower the claim when:

- WFO sign/rank is unstable
- signal concentrates in one short regime
- thresholds are knife-edge
- ONNX export or parity breaks
- trade density is too sparse or too dense for the decision use
- repeated work is only micro-tuning without a new surface clue

## Required Run Fields

Run-local manifests or receipts must record:

- ID chain
- `primary_family`
- `primary_skill`
- `support_skills`
- `required_gates`
- `required_gate_coverage`
- `storage_contract`
- `evidence_paths`
- `claim_boundary`
- `forbidden_claims`
- `runtime_learning_probe_decision`
- `result_judgment`
- `missing_evidence`
- `next_action`
