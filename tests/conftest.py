"""
conftest.py — shared pytest fixtures for bankquery-copilot-local tests.
Forces MOCK_MODE=1 so tests never need a live Foundry Local endpoint.
"""

import os
import sys

import pytest

# Ensure mock mode is always on during tests
os.environ["MOCK_MODE"] = "1"

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def finance_plan() -> dict:
    """A known-good Finance QueryPlan fixture."""
    return {
        "domain": "Finance",
        "intent": "Calculate Net Interest Margin by product for UK in Q1 2025",
        "dataset": "interest",
        "time_range": {"start": "2025-01-01", "end": "2025-03-31"},
        "filters": [{"field": "region", "op": "=", "value": "UK"}],
        "group_by": ["product"],
        "metrics": ["NII", "NIM"],
        "explanation_requirements": {
            "include_terms_used": True,
            "include_assumptions": True,
            "include_safety_notes": True,
        },
    }


@pytest.fixture
def risk_plan() -> dict:
    """A known-good Risk QueryPlan fixture."""
    return {
        "domain": "Risk",
        "intent": "Show loans migrated from Stage 1 to Stage 2 and compute ECL",
        "dataset": "loans",
        "time_range": {"start": "2024-12-28", "end": "2025-01-28"},
        "filters": [
            {"field": "stage_ifrs9", "op": "=", "value": 2},
            {"field": "previous_stage", "op": "=", "value": 1},
        ],
        "group_by": [],
        "metrics": ["ECL"],
        "explanation_requirements": {
            "include_terms_used": True,
            "include_assumptions": True,
            "include_safety_notes": True,
        },
    }


@pytest.fixture
def treasury_plan() -> dict:
    """A known-good Treasury QueryPlan fixture."""
    return {
        "domain": "Treasury",
        "intent": "Show monthly NSFR trend and flag months below 100%",
        "dataset": "liquidity",
        "filters": [{"field": "region", "op": "=", "value": "UK"}],
        "group_by": ["month"],
        "metrics": ["NSFR"],
        "post_processing": {
            "flag_threshold": 100.0,
            "sort_by": "month",
            "sort_order": "asc",
        },
        "explanation_requirements": {
            "include_terms_used": True,
            "include_assumptions": True,
            "include_safety_notes": True,
        },
    }


@pytest.fixture
def aml_plan() -> dict:
    """A known-good AML QueryPlan fixture."""
    return {
        "domain": "AML",
        "intent": "Find customers with repeated cash deposits near reporting threshold within 7 days",
        "dataset": "transactions",
        "filters": [{"field": "cash", "op": "=", "value": True}],
        "group_by": ["customer_id"],
        "metrics": ["STRUCTURING_FLAG"],
        "post_processing": {"window_days": 7, "min_count": 3},
        "explanation_requirements": {
            "include_terms_used": True,
            "include_assumptions": True,
            "include_safety_notes": True,
        },
    }


@pytest.fixture
def malformed_json() -> str:
    """Malformed JSON text for repair loop testing."""
    return '{"domain": "Finance", "intent": 123, "dataset": "wrong_dataset"}'


@pytest.fixture
def error_plan() -> dict:
    """A known-good error/refusal QueryPlan fixture."""
    return {
        "domain": "Finance",
        "intent": "error",
        "dataset": "interest",
        "error": {
            "type": "validation_error",
            "message": "Test error",
            "repair_attempted": True,
        },
    }
