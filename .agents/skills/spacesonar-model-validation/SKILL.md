---
name: spacesonar-model-validation
description: Validate model, threshold, calibration, split, WFO, overfit, and selection claims.
---

# SpaceSonar Model Validation

Use this skill when work touches model training, model selection, threshold selection, ranking, calibration, feature importance, WFO, or any claim that one model is better than another.

## Required Output

- `model_family`: model type, training script, or runtime bundle
- `target_and_label`: what the model predicts and how the label is built
- `split_method`: holdout, WFO, cross-validation, runtime probe, or other split
- `selection_metric`: metric used to choose the model or threshold
- `secondary_metrics`: metrics that can reveal hidden failure
- `threshold_policy`: fixed, searched, calibrated, or runtime-configured
- `overfit_risk`: most likely overfitting or multiple-testing path
- `calibration_risk`: whether scores mean probability, rank, or only ordering
- `top_n_selection_bias_check`: whether a top-ranked subset, hand-picked run, or post-hoc filter is driving the claim
- `threshold_knife_edge_check`: whether small threshold changes would erase the apparent result
- `segment_or_regime_stability_check`: whether performance is concentrated in one time, volatility, session, tier, or direction pocket
- `trade_concentration_check`: whether a small number of trades or outliers explain the headline KPI
- `wfo_or_window_dispersion`: whether comparable windows agree, disagree, or are missing
- `proxy_runtime_laundering_check`: whether proxy evidence is being overstated as MT5/runtime truth
- `risk_stop_check`: drawdown, exposure, stop/hold behavior, and adverse trade shape checks performed or missing
- `comparison_baseline`: previous model, no-trade baseline, random baseline, or manual rule
- `anti_authority_laundering_judgment`: whether the result stays exploratory/candidate instead of becoming baseline, pass, runtime authority, or live readiness
- `validation_judgment`: exploratory, candidate, inconclusive, invalid, blocked, or stronger project term allowed by policy

## Guardrails

- Do not promote a model because one threshold or one split looks good.
- Do not call a higher headline metric a model improvement unless selection bias, threshold sensitivity, segment concentration, trade shape, and drawdown risk are checked.
- Do not describe rank scores as probabilities unless calibration supports it.
- Do not let WFO absence kill exploration; downgrade the claim instead.
- Do not choose a threshold without naming what it optimizes and what it may harm.
- Challenge any result driven by a top-N selection, a narrow threshold band, one regime, one outlier trade cluster, or proxy-only evidence.
- If risk, concentration, or runtime-parity checks are missing, lower the judgment to exploratory or inconclusive.
- Do not promote a research candidate into selected baseline, economics pass, runtime authority, or live readiness without the required project evidence.
