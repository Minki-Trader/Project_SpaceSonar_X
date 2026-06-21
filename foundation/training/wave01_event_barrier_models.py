from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ProxyFit:
    model: Pipeline
    task_kind: str
    target_name: str
    threshold_policy: str
    target_threshold: float | None
    score_low_threshold: float | None
    score_high_threshold: float | None
    train_score_summary: dict[str, float]
    model_summary: dict[str, Any]


REGRESSION_LABEL_SURFACES = {
    "mfe_mae_path_quality_ratio",
    "volatility_shock_continuation",
    "extreme_timeout_path_quality",
}


def _finite_quantile(values: np.ndarray, q: float) -> float:
    clean = values[np.isfinite(values)]
    if clean.size == 0:
        return float("nan")
    return float(np.quantile(clean, q))


def _classification_target_from_raw_or_quantile(
    labels: pd.DataFrame,
    train_mask: pd.Series,
    *,
    quantile: float = 0.60,
) -> tuple[pd.Series, float | None, str]:
    raw = labels["target_binary_raw"].astype(float)
    train_raw = raw.loc[train_mask].dropna()
    if len(set(train_raw.astype(int).tolist())) >= 2:
        return raw.astype("Int64").astype(float), None, "target_binary_raw"
    train_values = labels.loc[train_mask, "target_continuous"].astype(float)
    threshold = float(train_values.quantile(quantile))
    return (labels["target_continuous"].astype(float) >= threshold).astype(float), threshold, f"target_continuous_train_q{int(quantile * 100)}"


def build_model_target(
    labels: pd.DataFrame,
    train_mask: pd.Series,
    *,
    label_surface: str,
    model_family: str,
    model_task: str,
) -> tuple[pd.Series, str, str, float | None]:
    if model_family == "logistic_or_linear_rank_scout" and (
        label_surface in REGRESSION_LABEL_SURFACES or "path_quality" in model_task
    ):
        return labels["target_continuous"].astype(float), "regression", "target_continuous", None
    if model_family in {
        "logistic_or_linear_rank_scout",
        "tree_or_boosted_onnx_feasible_scout",
        "small_mlp_secondary_only",
    }:
        target, threshold, target_name = _classification_target_from_raw_or_quantile(labels, train_mask)
        return target, "classification", target_name, threshold
    raise ValueError(f"unsupported Wave01 model_family: {model_family}")


def fit_proxy_model(
    features: pd.DataFrame,
    target: pd.Series,
    train_mask: pd.Series,
    *,
    model_family: str,
    task_kind: str,
    target_name: str,
    threshold_policy: str,
    target_threshold: float | None,
) -> ProxyFit:
    # ONNX and MT5 consume float32 tensors. Fit and score the proxy on the same
    # dtype to avoid tree-threshold boundary drift during materialization.
    runtime_features = features.astype("float32")
    x_train = runtime_features.loc[train_mask]
    y_train = target.loc[train_mask]
    if len(x_train) < 1000:
        raise ValueError(f"not enough train rows for Wave01 proxy model: {len(x_train)}")

    if task_kind == "regression":
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("ridge", Ridge(alpha=1.0)),
            ]
        )
    elif model_family == "logistic_or_linear_rank_scout":
        _assert_two_classes(y_train)
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("logistic", LogisticRegression(max_iter=500, class_weight="balanced", solver="lbfgs")),
            ]
        )
    elif model_family == "tree_or_boosted_onnx_feasible_scout":
        _assert_two_classes(y_train)
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "hist_gradient_boosting",
                    HistGradientBoostingClassifier(
                        max_iter=70,
                        learning_rate=0.05,
                        max_leaf_nodes=15,
                        l2_regularization=0.1,
                        random_state=0,
                    ),
                ),
            ]
        )
    elif model_family == "small_mlp_secondary_only":
        _assert_two_classes(y_train)
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "mlp",
                    MLPClassifier(
                        hidden_layer_sizes=(16,),
                        activation="relu",
                        alpha=0.001,
                        max_iter=60,
                        early_stopping=True,
                        random_state=0,
                    ),
                ),
            ]
        )
    else:
        raise ValueError(f"unsupported Wave01 model_family/task: {model_family}/{task_kind}")

    model.fit(x_train, y_train)
    train_scores = score_model(model, x_train, task_kind)
    low = _finite_quantile(train_scores, 0.20)
    high = _finite_quantile(train_scores, 0.80)
    if threshold_policy == "diagnostic_no_trade" or not np.isfinite(low) or not np.isfinite(high):
        low = high = None
    return ProxyFit(
        model=model,
        task_kind=task_kind,
        target_name=target_name,
        threshold_policy=threshold_policy,
        target_threshold=target_threshold,
        score_low_threshold=low,
        score_high_threshold=high,
        train_score_summary={
            "min": float(np.nanmin(train_scores)),
            "p20": _finite_quantile(train_scores, 0.20),
            "median": _finite_quantile(train_scores, 0.50),
            "p80": _finite_quantile(train_scores, 0.80),
            "max": float(np.nanmax(train_scores)),
        },
        model_summary={
            "model_family": model_family,
            "task_kind": task_kind,
            "target_name": target_name,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "threshold_policy": threshold_policy,
            "score_threshold_fit_scope": "train_only" if low is not None else "not_applicable",
            "preprocessing_fit_scope": "train_only",
            "calibration": "none",
            "selector": "none",
        },
    )


def _assert_two_classes(target: pd.Series) -> None:
    unique = sorted(set(target.dropna().astype(int).tolist()))
    if len(unique) < 2:
        raise ValueError(f"classification target has one train class: {unique}")


def score_model(model: Pipeline, features: pd.DataFrame, task_kind: str) -> np.ndarray:
    features = features.astype("float32")
    if task_kind == "classification":
        if hasattr(model, "predict_proba"):
            return model.predict_proba(features)[:, 1].astype(float)
        return model.decision_function(features).astype(float)
    return model.predict(features).astype(float)


def diagnostic_metrics(target: pd.Series, score: np.ndarray, task_kind: str) -> dict[str, Any]:
    target_clean = target.astype(float)
    metrics: dict[str, Any] = {
        "row_count": int(len(target_clean)),
        "score_mean": float(np.nanmean(score)),
        "score_std": float(np.nanstd(score)),
    }
    if task_kind == "classification":
        y_int = target_clean.astype(int)
        pred = (score >= 0.5).astype(int)
        metrics["accuracy"] = float(accuracy_score(y_int, pred))
        metrics["balanced_accuracy"] = float(balanced_accuracy_score(y_int, pred))
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_int, score))
        except ValueError:
            metrics["roc_auc"] = None
        try:
            metrics["average_precision"] = float(average_precision_score(y_int, score))
        except ValueError:
            metrics["average_precision"] = None
        try:
            metrics["log_loss"] = float(log_loss(y_int, np.clip(score, 1e-6, 1.0 - 1e-6)))
        except ValueError:
            metrics["log_loss"] = None
        metrics["positive_rate"] = float(np.mean(y_int))
    else:
        metrics["mae"] = float(mean_absolute_error(target_clean, score))
        metrics["rmse"] = float(mean_squared_error(target_clean, score) ** 0.5)
        score_series = pd.Series(score, index=target_clean.index)
        metrics["pearson_corr"] = _nullable_float(score_series.corr(target_clean, method="pearson"))
        metrics["spearman_corr"] = _nullable_float(score_series.corr(target_clean, method="spearman"))
        metrics["target_mean"] = float(target_clean.mean())
        metrics["target_std"] = float(target_clean.std())
    return metrics


def decision_metrics(
    *,
    decision_family: str,
    score: np.ndarray,
    labels: pd.DataFrame,
    fit: ProxyFit,
) -> dict[str, Any]:
    future_return = labels["future_return"].astype(float).to_numpy()
    high = fit.score_high_threshold
    low = fit.score_low_threshold
    metrics: dict[str, Any] = {
        "decision_family": decision_family,
        "threshold_policy": fit.threshold_policy,
        "threshold_fit_scope": "train_only" if high is not None else "not_applicable",
    }
    if "diagnostic_path_quality_no_trade" in decision_family:
        metrics.update(
            {
                "trade_count": 0,
                "trade_density": 0.0,
                "proxy_boundary": "diagnostic_only_no_trade_proxy",
            }
        )
        return metrics
    if high is None or low is None:
        metrics.update({"trade_count": 0, "trade_density": 0.0, "proxy_boundary": "threshold_unavailable"})
        return metrics

    side = np.zeros(len(score), dtype=float)
    if "no_trade" in decision_family or "direction_agnostic" in decision_family:
        active = score >= high
        gross_proxy_return = np.abs(future_return[active])
        metrics["proxy_boundary"] = "direction_agnostic_future_abs_return_proxy_no_cost_no_execution"
        metrics["hit_rate"] = _nullable_float(float(np.mean(labels["any_barrier_touch"].to_numpy()[active]))) if np.any(active) else None
    else:
        side[score >= high] = 1.0
        side[score <= low] = -1.0
        active = side != 0.0
        gross_proxy_return = side[active] * future_return[active]
        metrics["long_count"] = int(np.sum(side > 0.0))
        metrics["short_count"] = int(np.sum(side < 0.0))
        metrics["directional_accuracy"] = (
            float(np.mean(np.sign(future_return[active]) == side[active])) if np.any(active) else None
        )
        metrics["proxy_boundary"] = "gross_future_return_direction_proxy_no_cost_no_execution"

    positives = gross_proxy_return[gross_proxy_return > 0.0]
    negatives = gross_proxy_return[gross_proxy_return < 0.0]
    metrics["trade_count"] = int(np.sum(active))
    metrics["trade_density"] = float(np.mean(active)) if len(active) else 0.0
    metrics["gross_proxy_mean_return"] = float(np.mean(gross_proxy_return)) if gross_proxy_return.size else None
    metrics["gross_proxy_profit_factor"] = (
        float(np.sum(positives) / abs(np.sum(negatives))) if negatives.size and abs(np.sum(negatives)) > 0.0 else None
    )
    metrics["score_low_threshold"] = float(low)
    metrics["score_high_threshold"] = float(high)
    return metrics


def judge_proxy_result(
    validation_metrics: dict[str, Any],
    research_oos_metrics: dict[str, Any],
    validation_decision: dict[str, Any],
    research_oos_decision: dict[str, Any],
    task_kind: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if validation_metrics.get("row_count", 0) < 1000:
        return "invalid", ["too_few_validation_rows"]

    if task_kind == "classification":
        validation_auc = validation_metrics.get("roc_auc")
        research_auc = research_oos_metrics.get("roc_auc")
        if isinstance(validation_auc, float) and isinstance(research_auc, float):
            if validation_auc >= 0.53 and research_auc >= 0.51:
                reasons.append(f"validation_research_auc_preserved_clue_{validation_auc:.4f}_{research_auc:.4f}")
            elif validation_auc <= 0.48 and research_auc <= 0.50:
                reasons.append(f"validation_research_auc_negative_{validation_auc:.4f}_{research_auc:.4f}")
    else:
        validation_spearman = validation_metrics.get("spearman_corr")
        research_spearman = research_oos_metrics.get("spearman_corr")
        if isinstance(validation_spearman, float) and isinstance(research_spearman, float):
            if abs(validation_spearman) >= 0.04 and abs(research_spearman) >= 0.02:
                reasons.append(
                    f"validation_research_abs_spearman_preserved_clue_{validation_spearman:.4f}_{research_spearman:.4f}"
                )
            elif validation_spearman < -0.01 and research_spearman < -0.01:
                reasons.append(f"validation_research_spearman_negative_{validation_spearman:.4f}_{research_spearman:.4f}")

    for label, decision in [("validation", validation_decision), ("research_oos", research_oos_decision)]:
        trade_count = decision.get("trade_count") or 0
        gross_pf = decision.get("gross_proxy_profit_factor")
        if isinstance(gross_pf, float) and trade_count >= 500 and gross_pf >= 1.10:
            reasons.append(f"{label}_gross_proxy_pf_preserved_clue_{gross_pf:.4f}")

    if any("preserved_clue" in reason for reason in reasons):
        return "preserved_clue", reasons
    if reasons:
        return "negative", reasons
    return "inconclusive", ["valid_proxy_run_no_repeated_or_strong_surface_clue_yet_L4_still_required"]


def _nullable_float(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None
