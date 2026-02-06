"""
Deterministic executor: runs a QueryPlan over local JSON data files.
No model calls — pure Python computation.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_json(name: str) -> list[dict]:
    """Load a JSON data file by dataset name."""
    path = DATA_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_thresholds() -> list[dict]:
    return _load_json("thresholds")


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------

def _apply_filters(rows: list[dict], filters: list[dict]) -> list[dict]:
    """Apply a list of filter conditions to rows."""
    result = rows
    for flt in filters:
        field = flt["field"]
        op = flt["op"]
        value = flt["value"]
        result = [r for r in result if _match(r.get(field), op, value)]
    return result


def _match(field_val: Any, op: str, value: Any) -> bool:
    if field_val is None:
        return False
    if op == "=":
        return field_val == value
    if op == "!=":
        return field_val != value
    if op == ">":
        return field_val > value
    if op == "<":
        return field_val < value
    if op == ">=":
        return field_val >= value
    if op == "<=":
        return field_val <= value
    if op == "in":
        return field_val in value
    if op == "contains":
        return str(value).lower() in str(field_val).lower()
    return False


def _apply_time_range(rows: list[dict], time_range: dict | None, date_field: str) -> list[dict]:
    """Filter rows by time_range using the given date field."""
    if not time_range:
        return rows
    start = time_range.get("start", "")
    end = time_range.get("end", "")
    return [r for r in rows if start <= r.get(date_field, "") <= end]


def _group_rows(rows: list[dict], group_by: list[str]) -> dict[str, list[dict]]:
    """Group rows by the given fields. Returns dict of group_key -> rows."""
    if not group_by:
        return {"_all": rows}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = "|".join(str(r.get(g, "")) for g in group_by)
        groups[key].append(r)
    return dict(groups)


# ---------------------------------------------------------------------------
# Metric computations
# ---------------------------------------------------------------------------

def _compute_nii(rows: list[dict]) -> float:
    """Net Interest Income = sum(interest_income) - sum(interest_expense)."""
    income = sum(r.get("interest_income", 0) for r in rows)
    expense = sum(r.get("interest_expense", 0) for r in rows)
    return income - expense


def _compute_nim(rows: list[dict]) -> float:
    """Net Interest Margin = NII / avg_earning_assets (as percentage)."""
    nii = _compute_nii(rows)
    assets = sum(r.get("avg_earning_assets", 0) for r in rows)
    if assets == 0:
        return 0.0
    return round((nii / assets) * 100, 4)


def _compute_ecl(rows: list[dict]) -> list[dict]:
    """Expected Credit Loss = PD * LGD * EAD for each loan row."""
    results = []
    for r in rows:
        pd = r.get("pd", 0)
        lgd = r.get("lgd", 0)
        ead = r.get("ead", 0)
        ecl = round(pd * lgd * ead, 2)
        results.append({
            "loan_id": r.get("loan_id"),
            "customer_id": r.get("customer_id"),
            "product": r.get("product"),
            "stage_ifrs9": r.get("stage_ifrs9"),
            "previous_stage": r.get("previous_stage"),
            "pd": pd,
            "lgd": lgd,
            "ead": ead,
            "ecl": ecl,
        })
    return results


def _compute_nsfr(rows: list[dict]) -> list[dict]:
    """NSFR = available_stable_funding / required_stable_funding * 100."""
    results = []
    for r in rows:
        asf = r.get("available_stable_funding", 0)
        rsf = r.get("required_stable_funding", 0)
        nsfr = round((asf / rsf) * 100, 2) if rsf else 0
        results.append({
            "month": r.get("month"),
            "region": r.get("region"),
            "available_stable_funding": asf,
            "required_stable_funding": rsf,
            "nsfr_pct": nsfr,
            "breach": nsfr < 100,
        })
    return results


def _compute_structuring_flag(
    rows: list[dict],
    threshold: float,
    window_days: int = 7,
    min_count: int = 3,
) -> list[dict]:
    """
    Detect potential structuring / smurfing:
    - Cash deposits near threshold (>= 90% of threshold and < threshold)
    - Sliding window of window_days
    - Flag if count >= min_count per customer
    """
    near_threshold = [
        r for r in rows
        if r.get("cash", False)
        and r.get("amount", 0) >= (threshold * 0.9)
        and r.get("amount", 0) < threshold
    ]

    # Group by customer
    by_customer: dict[str, list[dict]] = defaultdict(list)
    for r in near_threshold:
        by_customer[r["customer_id"]].append(r)

    flagged = []
    for cust_id, txns in by_customer.items():
        txns_sorted = sorted(txns, key=lambda x: x["date"])
        # Sliding window check
        for i, txn in enumerate(txns_sorted):
            base_date = datetime.strptime(txn["date"], "%Y-%m-%d")
            window_txns = [
                t for t in txns_sorted
                if 0 <= (datetime.strptime(t["date"], "%Y-%m-%d") - base_date).days < window_days
            ]
            if len(window_txns) >= min_count:
                flagged.append({
                    "customer_id": cust_id,
                    "window_start": txn["date"],
                    "window_end": (base_date + timedelta(days=window_days - 1)).strftime("%Y-%m-%d"),
                    "count": len(window_txns),
                    "total_amount": sum(t["amount"] for t in window_txns),
                    "transactions": [t["transaction_id"] for t in window_txns],
                })
                break  # One flag per customer is sufficient for demo

    return flagged


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

def execute_query_plan(plan: dict) -> dict:
    """
    Execute a QueryPlan dict against local JSON data.
    Returns {results: [...], summary: {...}, safety_notes: [...]}.
    """
    if plan.get("intent") == "error":
        return {
            "results": [],
            "summary": {"error": plan.get("error", {}).get("message", "Unknown error")},
            "safety_notes": [],
        }

    dataset_name = plan.get("dataset", "interest")
    rows = _load_json(dataset_name)

    # Determine date field by dataset
    date_field_map = {
        "interest": "date",
        "loans": "last_updated",
        "liquidity": "month",
        "transactions": "date",
    }
    date_field = date_field_map.get(dataset_name, "date")

    # Apply time range
    time_range = plan.get("time_range")
    rows = _apply_time_range(rows, time_range, date_field)

    # Apply filters
    filters = plan.get("filters", [])
    rows = _apply_filters(rows, filters)

    metrics = plan.get("metrics", [])
    group_by = plan.get("group_by", [])
    post = plan.get("post_processing", {})

    results: list[dict] = []
    summary: dict[str, Any] = {"rows_matched": len(rows)}
    safety_notes: list[str] = []

    # --- NII / NIM (Finance) ---
    if "NII" in metrics or "NIM" in metrics:
        groups = _group_rows(rows, group_by)
        for key, grp in groups.items():
            entry: dict[str, Any] = {}
            if group_by:
                for i, g in enumerate(group_by):
                    entry[g] = key.split("|")[i] if "|" in key or len(group_by) == 1 else key
            if "NII" in metrics:
                entry["NII"] = _compute_nii(grp)
            if "NIM" in metrics:
                entry["NIM_pct"] = _compute_nim(grp)
            entry["record_count"] = len(grp)
            results.append(entry)
        summary["metric"] = "NII/NIM"
        safety_notes.append("NIM is annualised only if data covers a full period; partial-period values shown here.")

    # --- ECL (Risk) ---
    elif "ECL" in metrics:
        ecl_results = _compute_ecl(rows)
        results = ecl_results
        total_ecl = sum(r["ecl"] for r in ecl_results)
        summary["total_ecl"] = total_ecl
        summary["loans_count"] = len(ecl_results)
        safety_notes.append("ECL computed as simplified PD × LGD × EAD. Real IFRS 9 requires lifetime PD curves and discounting.")

    # --- NSFR (Treasury) ---
    elif "NSFR" in metrics:
        nsfr_results = _compute_nsfr(rows)
        flag_threshold = post.get("flag_threshold", 100.0)
        for r in nsfr_results:
            r["breach"] = r["nsfr_pct"] < flag_threshold
        # Sort
        sort_by = post.get("sort_by", "month")
        sort_order = post.get("sort_order", "asc")
        nsfr_results.sort(key=lambda x: x.get(sort_by, ""), reverse=(sort_order == "desc"))
        results = nsfr_results
        breaches = [r for r in nsfr_results if r["breach"]]
        summary["total_months"] = len(nsfr_results)
        summary["breach_months"] = len(breaches)
        safety_notes.append("NSFR below 100% indicates a potential breach of Basel III requirements. Regulatory action may be required.")

    # --- STRUCTURING_FLAG (AML) ---
    elif "STRUCTURING_FLAG" in metrics:
        # Load threshold for jurisdiction
        thresholds = _load_thresholds()
        threshold_val = 10000  # default
        for t in thresholds:
            if t.get("jurisdiction") == "UK" and t.get("currency") == "GBP":
                threshold_val = t["cash_reporting_threshold"]
                break

        window_days = post.get("window_days", 7)
        min_count = post.get("min_count", 3)
        results = _compute_structuring_flag(rows, threshold_val, window_days, min_count)
        summary["flagged_customers"] = len(results)
        summary["threshold_used"] = threshold_val
        summary["window_days"] = window_days
        summary["min_count"] = min_count
        safety_notes.append(
            "IMPORTANT: This is NOT a determination of wrongdoing. "
            "Flagged patterns are investigatory leads only and must be reviewed by a qualified AML analyst."
        )
        safety_notes.append(
            "Structuring detection heuristic: cash deposits >= 90% of reporting threshold, "
            f"occurring >= {min_count} times within a {window_days}-day window."
        )

    else:
        # Fallback: return filtered rows
        results = rows[:50]  # cap at 50
        summary["note"] = "No specific metric computation requested; returning filtered rows."

    return {
        "results": results,
        "summary": summary,
        "safety_notes": safety_notes,
    }
