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

- `lab/waves/<wave_id>/wave_allocation.yaml`
- `lab/waves/<wave_id>/campaign_refs.csv`
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

Wave/campaign ownership rule:

- A wave owns allocation, budget, sequencing, and campaign references.
- A campaign owns the experiment charter, surfaces, sweeps, and campaign-local parity policy.
- Campaign source-of-truth folders stay in central `lab/campaigns/<campaign_id>/`.
- Do not create `lab/waves/<wave_id>/campaigns/<campaign_id>/` as a second source of truth.
- Use `campaign_refs.csv` and `campaign.wave_ids` to bind central campaigns to waves.
- A wave or campaign must not become a long repair track for one candidate. Candidate-local fixes belong in bounded runs or sweeps. Repeated repair requires a reusable surface/divergence question, a new campaign, or closeout.
- Repair carryover cannot be relabeled as a fresh hypothesis in the next campaign or wave. A new campaign may inherit a repair only when the prior campaign records the exact new surface, divergence, or prevention-memory question that justifies it.

Git integration cadence:

- Durable commit/main-push boundaries are `campaign_open`, `campaign_close`, `wave_open`, and `wave_close`.
- Do not push every run to `main` by default.
- A boundary commit should include the matching source-of-truth manifest updates, registry/index updates, claim-boundary updates, and hash records for ignored heavy artifacts.
- Intermediate run work may stay branch-local or branch-committed, but it is not main-integrated evidence until the boundary commit/push is complete.

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
- Cost, heaviness, weak proxy results, low trade count, or imbalance are not standalone reasons to skip a narrow sufficient runtime probe.
- Research campaigns should be unexplored-surface discovery, not progressive single-axis optimization.
- A research campaign may emphasize one primary unknown, but it must keep companion axes visible: target/label, feature/input, model/training, decision, and horizon/holding/eval/runtime meaning.
- Waves and research campaigns must not be feature-only, label-only, model-only, threshold-only, or repair-only programs.
- Single-axis work is allowed only for control-plane, fixture, plumbing, parser, runtime micro-probe, or narrow bug-repair campaigns, and its claim boundary must say it is not research surface discovery.
- Every valid proxy/model-bearing run must be driven to `L4_split_runtime_probe`; proxy-only closure is not an allowed endpoint.
- If L4 still looks usable under the declared surface and execution profile, continue to `L5_candidate_runtime_evidence`.
- A planned proxy surface must include an executable ONNX/EA/MT5 follow-through path. If it cannot be made executable, repair the surface before treating it as proxy evidence.
- Missing converter, export adapter, EA adapter, parser support, or runtime glue is not by itself a valid closeout reason. First reproduce the failure, capture the root cause, attempt the smallest credible repair or fallback adapter, and record the attempt evidence. Only then may the item become `blocked_retry`, `invalid_setup`, `negative_memory`, or a lowered-boundary `inconclusive` record.
- Repair is for interpretation, parity, execution, or prevention memory. It is not permission to keep one weak candidate alive through wave/campaign budget.
- Neighborhood perturbation around a repair is allowed only while it tests meaningful adjacent semantics: unit conversion, parity mapping, execution interpretation, or directly neighboring surface variables. Stop when it becomes generic micro-tuning, candidate laundering, or a renamed continuation without new evidence.
- Parity is tracked per campaign from the first proxy-bearing run. Do not wait for a selected candidate before checking whether Python/proxy semantics, ONNX semantics, EA semantics, and MT5 tester semantics are still the same experiment.
- Parity is not forced equality. When proxy and MT5 disagree, make at least one explicit reconciliation attempt, then either repair the contract or record the accepted difference with a prevention rule.
- Failed hypotheses become `negative_memory`, `invalid_setup`, `blocked_retry`, or `inconclusive` records with salvage value and reopen conditions.

## Bounded Synthesis Campaign

A bounded synthesis campaign is the current-lab equivalent of a previous-material mixing sandbox. Do not use legacy stage language in active records.

Rules:

- Use `campaign_type: bounded_synthesis`.
- Source scope is previous material only: closed campaign clues, negative memory, divergence records, and run evidence from earlier campaigns.
- Ingredient cards are required. Each ingredient must name source campaign/run/clue/memory IDs, evidence paths, salvage value, and forbidden uses.
- A synthesis campaign may create learning records, reference surfaces, preserved clues, negative memory, divergence questions, or new surface questions.
- It must not direct the next wave, choose the next campaign theme, claim baseline status, or hide a repair continuation as a fresh hypothesis.
- Default mix depth is `mix-2 -> mix-3`.
- `mix-4` is exception-only and needs a recorded reason before opening the queue item.
- `mix-5+` is forbidden unless the project policy is explicitly changed.
- Every valid proxy/model-bearing synthesis run still follows the normal `L4_split_runtime_probe` requirement.
- If L4 remains promising, continue to `L5_candidate_runtime_evidence`.
- Closeout remains claim-boundary explicit: no selected baseline, runtime authority, economics pass, live readiness, reviewed/pass, or Goal Achieve without matching evidence.

## Campaign Parity Rule

Each campaign that creates proxy/model-bearing evidence must maintain a `proxy_runtime_parity` record or field.

Required contents:

- shared contract: dataset, row key, split, feature order, label, decision surface, threshold policy, holding/exit logic, cost assumptions, and tester profile
- known differences: proxy-only assumptions versus MT5 behavior
- interpretation drift risks: bar close timing, spread, commission, swap, slippage, fill rules, execution timing, no-trade behavior, rounding, lot sizing, symbol contract, and session handling
- minimum reconciliation attempt: at least one explicit repair, conversion, or interpretation check before closing the discrepancy
- unit semantics: point, pip, tick size, digits, price distance, ATR multiplier, lot step, volume, and rounding rules when they can change meaning
- comparison classes: proxy_good_runtime_good, proxy_good_runtime_bad, proxy_bad_runtime_bad, proxy_bad_runtime_good, invalid_or_unmaterializable
- divergence judgment: matched, expected_difference, unexplained_difference, mt5_surprise_positive, mt5_surprise_negative, invalid_setup, or blocked
- prevention memory: the reusable rule that prevents the same proxy-vs-MT5 mistake in later campaigns
- follow-up action: preserve clue, repair surface, invalidate setup, continue L5, or open a divergence campaign

Proxy failure does not remove the L4 obligation for a valid proxy/model-bearing run. If MT5 also fails, that is negative evidence. If MT5 unexpectedly works, that discrepancy becomes a preserved clue or new hypothesis surface. If proxy works but MT5 fails, treat it as an interpretation or execution drift until explained.

Example: if proxy ATR SL/TP uses `120/180` as point-like distances but MT5 interprets the same values through symbol `point`, `digits`, `tick_size`, or price-distance conversion differently, record the mismatch as unit semantics drift. The follow-up is not to claim parity failed and move on; the follow-up is to define the conversion rule for future ATR stop logic.

## Sweep Order

Default research flow:

1. Task-surface scout
2. Multi-axis surface coverage: label/target, feature/input, model/training, decision, horizon/holding, and eval/runtime meaning
3. Input/target/decision definition
4. Broad sweep
5. Extreme sweep
6. WFO or split-aware narrowing when a repeated clue exists
7. ONNX export and parity preflight for every valid proxy/model-bearing surface
8. Bundle materialization
9. Proxy-vs-runtime parity and divergence record
10. Mandatory L4 MT5 split runtime probe for every valid proxy/model-bearing surface
11. L5 candidate runtime evidence when L4 remains promising

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
- converter, export adapter, EA adapter, parser, or runtime support is missing and no root-cause plus repair-attempt record exists yet
- trade density is too sparse or too dense for the decision use
- repeated work is only micro-tuning without a new surface clue
- a single candidate consumes repeated repair budget without producing reusable surface knowledge, parity prevention memory, or a divergence hypothesis
- a repair or neighborhood perturbation is being moved to another campaign/wave without an explicit new surface, divergence, or prevention-memory record

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
- `proxy_runtime_parity`
- `result_judgment`
- `missing_evidence`
- `next_action`
