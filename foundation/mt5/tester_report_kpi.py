from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.mt5.tester_report_receipt import decode_report_bytes, file_sha256  # noqa: E402


@dataclass(frozen=True)
class TesterReportMetric:
    metric_id: str
    labels: tuple[str, ...]
    value_type: str
    unit: str
    value_part: str = "first_number"


TESTER_REPORT_METRICS: tuple[TesterReportMetric, ...] = (
    TesterReportMetric("mt5.tester_report.bars", ("Bars in test", "Bars", "봉수"), "int", "bars"),
    TesterReportMetric("mt5.tester_report.ticks", ("Ticks", "틱"), "int", "ticks"),
    TesterReportMetric("mt5.tester_report.total_net_profit", ("Total Net Profit", "총수입"), "float", "account_currency"),
    TesterReportMetric("mt5.tester_report.gross_profit", ("Gross Profit", "누적 수익"), "float", "account_currency"),
    TesterReportMetric("mt5.tester_report.gross_loss", ("Gross Loss", "누적 손실"), "float", "account_currency"),
    TesterReportMetric("mt5.tester_report.profit_factor", ("Profit Factor",), "float", "ratio"),
    TesterReportMetric("mt5.tester_report.expected_payoff", ("Expected Payoff", "예상 비용"), "float", "account_currency"),
    TesterReportMetric("mt5.tester_report.recovery_factor", ("Recovery Factor",), "float", "ratio"),
    TesterReportMetric("mt5.tester_report.sharpe_ratio", ("Sharpe Ratio",), "float", "ratio"),
    TesterReportMetric("mt5.tester_report.total_trades", ("Total Trades", "총 거래횟수"), "int", "trades"),
    TesterReportMetric(
        "mt5.tester_report.balance_drawdown_maximal_amount",
        ("Balance Drawdown Maximal",),
        "float",
        "account_currency",
    ),
    TesterReportMetric(
        "mt5.tester_report.balance_drawdown_maximal_pct",
        ("Balance Drawdown Maximal",),
        "float",
        "percent",
        value_part="parenthetical_percent",
    ),
    TesterReportMetric(
        "mt5.tester_report.equity_drawdown_maximal_amount",
        ("Equity Drawdown Maximal",),
        "float",
        "account_currency",
    ),
    TesterReportMetric(
        "mt5.tester_report.equity_drawdown_maximal_pct",
        ("Equity Drawdown Maximal",),
        "float",
        "percent",
        value_part="parenthetical_percent",
    ),
    TesterReportMetric("mt5.tester_report.correlation_profits_mfe", ("Correlation (Profits,MFE)",), "float", "ratio"),
    TesterReportMetric("mt5.tester_report.correlation_profits_mae", ("Correlation (Profits,MAE)",), "float", "ratio"),
    TesterReportMetric("mt5.tester_report.correlation_mfe_mae", ("Correlation (MFE,MAE)",), "float", "ratio"),
)


class TableCellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._cell_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "tr":
            self._current_row = []
        elif lowered in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
            self._cell_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            text = normalize_cell_text("".join(self._current_cell))
            self._current_row.append(text)
            self._current_cell = None
            self._cell_depth = max(0, self._cell_depth - 1)
        elif lowered == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None
            self._current_cell = None
            self._cell_depth = 0

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)


def normalize_cell_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_label(value: str) -> str:
    return normalize_cell_text(value).rstrip(":=").strip().casefold()


def label_value_pairs(rows: list[list[str]]) -> dict[str, list[str]]:
    pairs: dict[str, list[str]] = {}
    for row in rows:
        cells = [cell for cell in row if cell != ""]
        index = 0
        while index + 1 < len(cells):
            label = normalize_label(cells[index])
            value = cells[index + 1].strip()
            if label and value:
                pairs.setdefault(label, []).append(value)
            index += 2
    return pairs


def metric_value(raw_value: str, metric: TesterReportMetric) -> str | None:
    if metric.value_part == "parenthetical_percent":
        match = re.search(r"\(([-+]?\d[\d,]*(?:\.\d+)?)\s*%\)", raw_value)
        if not match:
            return None
        number = match.group(1)
    else:
        match = re.search(r"[-+]?\d[\d,\s]*(?:\.\d+)?", raw_value)
        if not match:
            return None
        number = match.group(0)
    normalized = re.sub(r"[\s,]+", "", number)
    if metric.value_type == "int":
        return str(int(float(normalized)))
    if metric.value_type == "float":
        return f"{float(normalized):.12g}"
    return normalized


def read_report_rows(path: Path) -> tuple[list[list[str]], str | None]:
    try:
        raw = path.read_bytes()
    except OSError:
        return [], "report_read_failed"
    text = decode_report_bytes(raw)
    if text is None:
        return [], "report_decode_failed"
    parser = TableCellParser()
    try:
        parser.feed(text)
    except Exception:
        return [], "report_html_parse_failed"
    if not parser.rows:
        return [], "report_table_rows_missing"
    return parser.rows, None


def parse_tester_report_kpis(path: Path) -> dict[str, Any]:
    rows, error = read_report_rows(path)
    if error:
        return {
            "version": "mt5_tester_report_kpi_parse_v1",
            "parse_status": "parser_failed",
            "source_report_path": str(path),
            "source_report_sha256": file_sha256(path) if path.exists() else "",
            "metrics": {},
            "missing_metrics": [metric.metric_id for metric in TESTER_REPORT_METRICS],
            "parser_diagnostic": (
                f"{error};repair_required=inspect tester report encoding/html structure;"
                "fallback_required=export CSV/XML report or update label aliases before accepted n/a"
            ),
        }
    pairs = label_value_pairs(rows)
    metrics: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for metric in TESTER_REPORT_METRICS:
        raw_value = None
        matched_label = None
        for label in metric.labels:
            values = pairs.get(normalize_label(label))
            if values:
                raw_value = values[0]
                matched_label = label
                break
        if raw_value is None:
            missing.append(metric.metric_id)
            continue
        parsed = metric_value(raw_value, metric)
        if parsed is None:
            missing.append(metric.metric_id)
            continue
        metrics[metric.metric_id] = {
            "metric_value": parsed,
            "value_type": metric.value_type,
            "unit": metric.unit,
            "raw_value": raw_value,
            "matched_label": matched_label,
        }
    return {
        "version": "mt5_tester_report_kpi_parse_v1",
        "parse_status": "parsed",
        "source_report_path": str(path),
        "source_report_sha256": file_sha256(path),
        "metrics": metrics,
        "missing_metrics": missing,
        "parser_diagnostic": "tester_report_kpi_parser_v1:html_table_label_value_pairs",
    }


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["metric_id", "metric_value", "value_type", "unit", "raw_value", "matched_label"],
            lineterminator="\n",
        )
        writer.writeheader()
        for metric_id, item in sorted((payload.get("metrics") or {}).items()):
            writer.writerow(
                {
                    "metric_id": metric_id,
                    "metric_value": item.get("metric_value", ""),
                    "value_type": item.get("value_type", ""),
                    "unit": item.get("unit", ""),
                    "raw_value": item.get("raw_value", ""),
                    "matched_label": item.get("matched_label", ""),
                }
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse MT5 Strategy Tester report KPI fields.")
    parser.add_argument("report_path")
    parser.add_argument("--summary-out")
    parser.add_argument("--csv-out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = parse_tester_report_kpis(Path(args.report_path))
    if args.summary_out:
        write_yaml(Path(args.summary_out), payload)
    if args.csv_out:
        write_csv(Path(args.csv_out), payload)
    print(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False))
    return 0 if payload["parse_status"] == "parsed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
