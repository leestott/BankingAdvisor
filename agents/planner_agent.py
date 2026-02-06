"""
QueryPlannerAgent — deterministic agent that constructs the structural
parameters for a QueryPlan (dataset, time_range, group_by, filters) based
on ontology output and simple prompt parsing. No LLM calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from agents.base import AgentMessage, BaseAgent


# Date range detection patterns
_QUARTER_RE = re.compile(r"Q([1-4])\s*(\d{4})", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{4})\b",
    re.IGNORECASE,
)
_LAST_N_DAYS_RE = re.compile(r"(?:last|past)\s+(\d+)\s+days?", re.IGNORECASE)

# Region detection
_REGION_MAP = {
    "uk": "UK",
    "united kingdom": "UK",
    "eu": "EU",
    "europe": "EU",
    "us": "US",
    "united states": "US",
}

# Product keywords
_PRODUCT_KEYWORDS = ["mortgage", "sme loan", "credit card"]


def _detect_time_range(text: str) -> dict | None:
    """Try to extract a date range from natural language."""
    lower = text.lower()

    # "last N days"
    m = _LAST_N_DAYS_RE.search(lower)
    if m:
        days = int(m.group(1))
        end = datetime(2025, 1, 28)  # reference date for demo
        start = end - timedelta(days=days)
        return {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")}

    # "Q1 2025"
    m = _QUARTER_RE.search(text)
    if m:
        q = int(m.group(1))
        y = int(m.group(2))
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        # Last day of end month
        if end_month == 12:
            end_day = 31
        elif end_month in (1, 3, 5, 7, 8, 10):
            end_day = 31
        elif end_month in (4, 6, 9, 11):
            end_day = 30
        else:
            end_day = 28
        return {
            "start": f"{y}-{start_month:02d}-01",
            "end": f"{y}-{end_month:02d}-{end_day:02d}",
        }

    return None


def _detect_region(text: str) -> str | None:
    lower = text.lower()
    for kw, region in _REGION_MAP.items():
        if kw in lower:
            return region
    return None


def _detect_product(text: str) -> str | None:
    lower = text.lower()
    for p in _PRODUCT_KEYWORDS:
        if p in lower:
            return p.title()
    return None


class QueryPlannerAgent(BaseAgent):
    name = "QueryPlannerAgent"
    description = "Constructs structural query plan parameters from ontology output and prompt."

    async def run(self, message: AgentMessage) -> AgentMessage:
        prompt_text = message.content
        ont = message.data  # from OntologyAgent

        domain = ont.get("domain", "Finance")
        metrics = ont.get("metrics", [])
        dataset = ont.get("dataset", "interest")

        # Build filters
        filters: list[dict] = []
        region = _detect_region(prompt_text)
        if region:
            filters.append({"field": "region", "op": "=", "value": region})

        product = _detect_product(prompt_text)
        if product:
            filters.append({"field": "product", "op": "=", "value": product})

        # For AML, ensure cash filter
        if "STRUCTURING_FLAG" in metrics:
            filters.append({"field": "cash", "op": "=", "value": True})

        # For Risk/ECL stage migration
        if "ECL" in metrics:
            # Detect stage migration request
            lower = prompt_text.lower()
            if "stage 1" in lower and "stage 2" in lower:
                filters.append({"field": "stage_ifrs9", "op": "=", "value": 2})
                filters.append({"field": "previous_stage", "op": "=", "value": 1})

        # Time range
        time_range = _detect_time_range(prompt_text)

        # Group by
        group_by: list[str] = []
        lower = prompt_text.lower()
        if "by product" in lower or "per product" in lower:
            group_by.append("product")
        if "by region" in lower or "per region" in lower:
            group_by.append("region")
        if "monthly" in lower or "month" in lower or "trend" in lower:
            group_by.append("month")
        if "by customer" in lower or "per customer" in lower:
            group_by.append("customer_id")

        # Post processing
        post_processing: dict = {}
        if "NSFR" in metrics:
            post_processing["flag_threshold"] = 100.0
            post_processing["sort_by"] = "month"
            post_processing["sort_order"] = "asc"
        if "STRUCTURING_FLAG" in metrics:
            post_processing["window_days"] = 7
            post_processing["min_count"] = 3

        plan_skeleton = {
            "domain": domain,
            "intent": prompt_text[:200],
            "dataset": dataset,
            "metrics": metrics,
            "filters": filters,
            "group_by": group_by,
            "time_range": time_range,
            "post_processing": post_processing if post_processing else None,
            "explanation_requirements": {
                "include_terms_used": True,
                "include_assumptions": True,
                "include_safety_notes": True,
            },
        }
        # Remove None values
        plan_skeleton = {k: v for k, v in plan_skeleton.items() if v is not None}

        return AgentMessage(
            role="agent",
            content=f"Plan skeleton built for {domain}/{metrics}",
            data={"plan_skeleton": plan_skeleton, "prompt_text": prompt_text},
            source_agent=self.name,
        )
