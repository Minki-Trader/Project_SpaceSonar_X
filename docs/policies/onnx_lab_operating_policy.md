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

- Work on `main` by default; routine `codex/` work branches are disabled unless
  the user explicitly requests one.
- Durable `origin/main` push boundaries are `campaign_close`, `wave_close`, and
  explicit user-approved stabilization points.
- Do not push every run to `origin/main` by default.
- A boundary commit should include the matching source-of-truth manifest updates, registry/index updates, claim-boundary updates, and hash records for ignored heavy artifacts.
- Intermediate run work may stay as unpushed local `main` commits or dirty
  working-tree output, but it is not remote main-integrated evidence until the
  boundary commit/push is complete.

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
- Try-first disposition rule: do not close a surface as blocked, deferred, invalid, or discarded until the failure reason is identified, the failing layer is reproduced, a smallest credible repair/fallback under repo control is attempted, and the evidence/reopen condition is recorded.
- The operating posture is attempt-first: when something does not work, Codex must find out why and make the smallest credible repo-controlled attempt before deciding it is not usable.
- Explanation-only closeout is forbidden. A diagnosis, advisory note, missing-helper observation, or agent consensus does not count as an attempt. Use the smallest concrete fixture, parser run, conversion shim, EA/ONNX glue patch, compile, command, or MT5 micro-probe that can test the failure before lowering the claim.
- Missing converter, conversion adapter, export adapter, EA adapter, parser support, or runtime glue is not by itself a valid closeout reason. First reproduce the failure and capture the root cause.
- If the missing piece is under repo/control, build and test the smallest credible repair or fallback adapter. "Adapter absent" is not a blocker.
- If a needed conversion adapter does not exist, create the smallest explicit translation layer needed to test the hypothesis. Only narrow feasibility exceptions may stop that attempt.
- If the attempt cannot be made because it needs user secrets, unavailable external state, destructive/unsafe action, or violates project policy, record that exact attempt blocker with evidence and a reopen condition.
- Only after this may the item become `blocked_retry`, `invalid_setup`, `negative_memory`, or a lowered-boundary `inconclusive` record.
- Repair is for interpretation, parity, execution, or prevention memory. It is not permission to keep one weak candidate alive through wave/campaign budget.
- Neighborhood perturbation around a repair is allowed only while it tests meaningful adjacent semantics: unit conversion, parity mapping, execution interpretation, or directly neighboring surface variables. Stop when it becomes generic micro-tuning, candidate laundering, or a renamed continuation without new evidence.
- Parity is tracked per campaign from the first proxy-bearing run. Do not wait for a selected candidate before checking whether Python/proxy semantics, ONNX semantics, EA semantics, and MT5 tester semantics are still the same experiment.
- Parity is not forced equality. When proxy and MT5 disagree, make at least one explicit reconciliation attempt, then either repair the contract or record the accepted difference with a prevention rule.
- Failed hypotheses become `negative_memory`, `invalid_setup`, `blocked_retry`, or `inconclusive` records with salvage value and reopen conditions.

## KPI Interpretation

KPI-bearing results, campaign closeouts, wave closeouts, and candidate comparisons must interpret what was tested, not only report what number appeared.

Required interpretation chain:

- tested factor or changed variable
- KPI scope: proxy, MT5 runtime, proxy-vs-MT5 comparison, or mixed
- observed KPI movement versus the declared comparison baseline
- exploratory effect hypothesis: what the tested factor appears to do
- segment checks performed or missing
- evidence limits and alternative explanations
- attribution confidence
- smallest next probe that can confirm or reject the explanation

KPI ledgers and closeouts must include both overall KPI and segment breakdowns. Required segment axes are:

- overall
- period role: validation, research_oos, or other declared period role
- time window
- session
- direction: long, short, flat, or no-trade
- score or threshold bucket
- trade shape bucket
- runtime surface: proxy, MT5 runtime, or proxy-vs-MT5 comparison

Optional segment axes include volatility regime, drawdown cluster, holding period bucket, feature family, target family, model family, and spread or cost bucket.

If a required segment cannot be materialized from the current evidence, the KPI summary must still name the segment and record it as missing or not collected with a reason and the next materialization step. Do not create placeholder segment analysis: observed or partial segments must name the metric/count basis they came from. Segment results explain instability, concentration, and the next probe; they must not be used by themselves to claim selected baseline, economics pass, runtime authority, live readiness, reviewed/pass, or Goal Achieve.

Outcome-only closeout is incomplete. If the changed variable, baseline, sample scope, or runtime evidence is missing, lower the interpretation to low-confidence or inconclusive. Do not claim a causal effect unless controls, matched scope, sufficient samples, and matching proxy/runtime evidence support it.

## Execution Weight

The lab is attempt-first, not bureaucracy-first.

- Start each new surface, repair, adapter, or runtime glue path with the smallest execution that can answer the immediate question.
- Use a thin first pass: one fixture, one representative run, one export smoke, one parser smoke, or one MT5 micro-path when that is enough to prove or falsify the path.
- Scale to broader execution only after the thin path is real, the surface remains useful, or the claim boundary requires it.
- Keep project-wide synchronization proportional. Full pytest, full active-record validation, global registry regeneration, and broad hash sync are for shared-contract edits, source-of-truth drift, campaign/wave boundary closeout, or protected runtime/economics/handoff claims.
- Main push defaults to a fast remote smoke layer: policy/routing lints,
  repository setting check, registry projection check, whitespace check, and a
  non-pytest compile/parse smoke set.
- `ci-scope-gate` classifies changed paths on main push in advisory mode. It is
  allowed to say that a manual boundary check is needed, but it must not turn
  every run-local update into a blocking full-regression wait.
- `evidence-graph-full` is manual `workflow_dispatch` evidence for campaign
  closeout, wave closeout, source-of-truth drift, or protected runtime,
  economics, handoff, reviewed/pass, selected-baseline, production, or live
  readiness claim changes.
- Full regression remains manual `workflow_dispatch` evidence for shared source,
  dependency, validator, policy, workflow, or protected-claim changes when the
  focused checks do not cover the blast radius.
- For ordinary run-local learning, update the local manifest, receipt, lineage, metrics, or campaign-local summary first. Global indexes can wait until the boundary unless the index is the current source of truth.
- The mandatory L4 rule still stands for every valid proxy/model-bearing run. It may be executed in bounded materialization and probe batches rather than folded into the first proxy or adapter attempt.
- L4 budget accounting uses the `validation_research_oos_pair` unit. One L4 budget unit means the same declared cell/surface/runtime-surface has both required period roles: `validation` and `research_oos`.
- `prepared_attempt_count`, `executed_attempt_count`, and `runtime_probe_complete_count` count physical Strategy Tester period-role executions. They are coverage and evidence counts, not the wave L4 budget burn.
- A standard L4 pair normally creates two physical MT5 executions. Decision replay uses the same period-role pair shape, but it must be counted in its own declared decision-replay pair ledger unless a wave explicitly budgets it together with standard L4.
- Historical fields named like `formal_mt5_strategy_tester_runs` are not hard L4 budget caps when an active `l4_budget_unit` or wave budget accounting amendment exists. Prefer `l4_pair_budget`, `l4_pair_count`, and `l4_pair_budget_usage` for new records.
- A minimal adapter is not a shortcut to claim success. It only proves that the path can be tested; stronger claims still need the matching evidence.

## Wave Budget Allocation

Wave budgets use a fixed-wave, variable-campaign allocation model.

Rules:

- The wave-level budget envelope is fixed before the wave opens.
- The standard wave profile is `standard_wave`.
- Standard wave run budget is 72 proxy/model-bearing run slots.
- Standard wave campaign slots are 3.
- Standard L4 budget is 36 `validation_research_oos_pair` units.
- Campaign and hypothesis budgets may vary inside the wave envelope because hypotheses differ in search width, setup cost, and uncertainty.
- Per-campaign run budget must stay within the declared campaign bounds unless the wave opens with an explicit budget exception.
- Default campaign bounds are minimum 8 runs, default 18 runs, and maximum 30 runs.
- Every campaign allocation must record an allocation reason before execution.
- Campaign or hypothesis allocation that is above or below the default must also explain why it deviates from the default.
- The reason must say which hypothesis surface needs the declared search width and which axes are held fixed.
- New or open wave records must use the standard allocation mode. Legacy closed Wave01-style soft budgets may remain as compatibility records only; they do not define the current operating pattern.
- A retrofitted legacy wave closeout must not hide unused active budget behind
  `retired` wording. It must either execute the declared active budget or
  explicitly re-declare an actualized retrofit budget that matches the durable
  materialized content. Future waves cannot use this retrofit exception; their
  budget is fixed before wave open.
- Standard campaign allocations must not exceed the standard campaign slot count unless the wave opens with an explicit budget exception.
- Mid-wave budget increases are not normal operation. If more budget is needed, open a new wave or record an explicit budget amendment with reason, user approval, and claim boundary.
- Wave-to-wave KPI comparisons use the wave-level budget envelope, not the individual campaign allocation amounts.
- Decision replay stays in a separate pair ledger unless the wave explicitly budgets it together with standard L4.

## Attempt Before Disposition

This is a global operating rule, not only a runtime rule.

- A failed, unsupported, missing, or nonworking path starts as `investigation_in_progress`.
- Before `blocked`, `deferred`, `invalid`, or `discarded`, Codex must identify the failure reason, reproduce or bound the failing layer, try the smallest repo-controlled repair/adapter/fallback, and record the evidence.
- `deferred` or `discarded` means the attempt record has shown why continuing is not justified inside the current bounded scope; it is not a shortcut for untried work.
- "Cannot", "unsupported", "not available", missing helper, missing adapter, missing parser, missing runner, missing converter, missing EA glue, or agent consensus is diagnosis only.
- When the missing layer is repo-controlled, the next action is to create or patch the smallest concrete translation/support layer needed to test the hypothesis.
- The repair attempt may be skipped only for user secrets, unavailable external state, destructive or unsafe action, or project-policy violation. The exception must be recorded as the attempt blocker with evidence and reopen condition.
- Discarding or deferring is valid only when the repair/fallback attempt or narrow blocker proves that continuing would require a new surface question, external state, unsafe action, or user decision.

## Bounded Synthesis Campaign

A bounded synthesis campaign is the current-lab equivalent of a previous-material mixing sandbox. Do not use legacy stage language in active records.

Rules:

- Use `campaign_type: bounded_synthesis`.
- Operating cadence is five completed standard campaign closeouts since the last bounded synthesis campaign before opening a new bounded synthesis campaign, unless a recorded exception is approved before open.
- Counted cadence items must be real closed standard campaigns with closeout evidence, not bare IDs.
- Source scope is previous material only: closed campaign clues, negative memory, divergence records, and run evidence from earlier campaigns.
- Ingredient cards are required. Each ingredient must name source campaign/run/clue/memory IDs, evidence paths, salvage value, and forbidden uses. Missing evidence paths or source IDs make the ingredient unusable for closeout.
- Raw ingredient cards consumed by a completed bounded synthesis campaign are not reused by default. A later synthesis campaign may see only carry-forward ingredients or a reopened ingredient with an explicit exception reason.
- A synthesis campaign may create learning records, reference surfaces, preserved clues, negative memory, divergence questions, or new surface questions.
- It must not direct the next wave, choose the next campaign theme, claim baseline status, or hide a repair continuation as a fresh hypothesis.
- Default mix depth is `mix-2 -> mix-3`.
- `mix-4` is exception-only and needs a recorded reason before opening the queue item.
- `mix-5+` is forbidden unless the project policy is explicitly changed.
- Every valid proxy/model-bearing synthesis run still follows the normal `L4_split_runtime_probe` requirement.
- If L4 remains promising, continue to `L5_candidate_runtime_evidence`.
- KPI ledgers use the same fixed schema as ordinary campaign and wave records. Synthesis KPI rows must use `stage_kind: special_mixing` and keep proxy, MT5 runtime, and proxy-vs-MT5 comparison ledgers separated.
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

`advisory_queue` means waiting for local Codex/user review or repo-controlled evidence. It is not reviewed, verified, pass, or selected. Task Force/sub-agent review is no longer an active workflow.

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
