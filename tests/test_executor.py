"""
test_executor.py — validate that each demo scenario produces non-empty results
from the deterministic executor.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.executor import execute_query_plan


class TestFinanceExecution:
    """Demo 1: Net Interest Margin."""

    def test_nim_produces_results(self, finance_plan):
        result = execute_query_plan(finance_plan)
        assert len(result["results"]) > 0, "Finance NIM should produce results"

    def test_nim_has_metric_fields(self, finance_plan):
        result = execute_query_plan(finance_plan)
        for row in result["results"]:
            assert "NII" in row, "Each row should have NII"
            assert "NIM_pct" in row, "Each row should have NIM_pct"

    def test_nim_grouped_by_product(self, finance_plan):
        result = execute_query_plan(finance_plan)
        products = {r.get("product") for r in result["results"]}
        assert "Mortgage" in products
        assert "SME Loan" in products
        assert "Credit Card" in products


class TestRiskExecution:
    """Demo 2: IFRS 9 stage migration + ECL."""

    def test_ecl_produces_results(self, risk_plan):
        result = execute_query_plan(risk_plan)
        assert len(result["results"]) > 0, "Risk ECL should produce results"

    def test_ecl_has_metric_fields(self, risk_plan):
        result = execute_query_plan(risk_plan)
        for row in result["results"]:
            assert "ecl" in row, "Each row should have ecl"
            assert "pd" in row
            assert "lgd" in row
            assert "ead" in row

    def test_ecl_formula_correct(self, risk_plan):
        result = execute_query_plan(risk_plan)
        for row in result["results"]:
            expected = round(row["pd"] * row["lgd"] * row["ead"], 2)
            assert row["ecl"] == expected, f"ECL mismatch: {row['ecl']} != {expected}"

    def test_ecl_only_stage_migrated(self, risk_plan):
        result = execute_query_plan(risk_plan)
        for row in result["results"]:
            assert row["stage_ifrs9"] == 2
            assert row["previous_stage"] == 1


class TestTreasuryExecution:
    """Demo 3: NSFR trend."""

    def test_nsfr_produces_results(self, treasury_plan):
        result = execute_query_plan(treasury_plan)
        assert len(result["results"]) > 0, "Treasury NSFR should produce results"

    def test_nsfr_has_breach_flag(self, treasury_plan):
        result = execute_query_plan(treasury_plan)
        for row in result["results"]:
            assert "nsfr_pct" in row
            assert "breach" in row
            assert isinstance(row["breach"], bool)

    def test_nsfr_breach_detection(self, treasury_plan):
        result = execute_query_plan(treasury_plan)
        breach_months = [r for r in result["results"] if r["breach"]]
        # Based on demo data, at least some months should breach
        assert len(breach_months) > 0, "Should detect at least one NSFR breach"

    def test_nsfr_sorted_by_month(self, treasury_plan):
        result = execute_query_plan(treasury_plan)
        months = [r["month"] for r in result["results"]]
        assert months == sorted(months), "Results should be sorted by month asc"


class TestAMLExecution:
    """Demo 4: Structuring / smurfing detection."""

    def test_structuring_produces_results(self, aml_plan):
        result = execute_query_plan(aml_plan)
        assert len(result["results"]) > 0, "AML structuring should flag some customers"

    def test_structuring_has_required_fields(self, aml_plan):
        result = execute_query_plan(aml_plan)
        for row in result["results"]:
            assert "customer_id" in row
            assert "count" in row
            assert "total_amount" in row
            assert "transactions" in row

    def test_structuring_min_count(self, aml_plan):
        result = execute_query_plan(aml_plan)
        min_count = aml_plan["post_processing"]["min_count"]
        for row in result["results"]:
            assert row["count"] >= min_count, f"Count {row['count']} < min_count {min_count}"

    def test_structuring_safety_notes(self, aml_plan):
        result = execute_query_plan(aml_plan)
        notes = result.get("safety_notes", [])
        assert len(notes) > 0, "AML results should include safety notes"
        assert any("not a determination" in n.lower() for n in notes)


class TestErrorPlanExecution:
    """Error plans should execute gracefully."""

    def test_error_plan_returns_empty(self, error_plan):
        result = execute_query_plan(error_plan)
        assert result["results"] == []
        assert "error" in result["summary"]
