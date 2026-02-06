"""
test_schema.py — validate that QueryPlan fixtures conform to the JSON Schema.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.schema_validate import validate_query_plan, parse_and_validate, build_error_plan


class TestSchemaValidation:
    """Ensure well-formed QueryPlans pass schema validation."""

    def test_finance_plan_valid(self, finance_plan):
        is_valid, errors = validate_query_plan(finance_plan)
        assert is_valid, f"Finance plan invalid: {errors}"

    def test_risk_plan_valid(self, risk_plan):
        is_valid, errors = validate_query_plan(risk_plan)
        assert is_valid, f"Risk plan invalid: {errors}"

    def test_treasury_plan_valid(self, treasury_plan):
        is_valid, errors = validate_query_plan(treasury_plan)
        assert is_valid, f"Treasury plan invalid: {errors}"

    def test_aml_plan_valid(self, aml_plan):
        is_valid, errors = validate_query_plan(aml_plan)
        assert is_valid, f"AML plan invalid: {errors}"

    def test_error_plan_valid(self, error_plan):
        is_valid, errors = validate_query_plan(error_plan)
        assert is_valid, f"Error plan invalid: {errors}"

    def test_invalid_domain_rejected(self):
        bad = {
            "domain": "InvalidDomain",
            "intent": "test",
            "dataset": "interest",
        }
        is_valid, errors = validate_query_plan(bad)
        assert not is_valid
        assert any("domain" in e for e in errors)

    def test_missing_required_fields_rejected(self):
        bad = {"domain": "Finance"}
        is_valid, errors = validate_query_plan(bad)
        assert not is_valid

    def test_invalid_dataset_rejected(self):
        bad = {
            "domain": "Finance",
            "intent": "test",
            "dataset": "nonexistent",
        }
        is_valid, errors = validate_query_plan(bad)
        assert not is_valid


class TestParseAndValidate:
    """Test parsing raw JSON text and validating."""

    def test_valid_json_string(self, finance_plan):
        raw = json.dumps(finance_plan)
        is_valid, plan, errors = parse_and_validate(raw)
        assert is_valid
        assert plan is not None
        assert plan["domain"] == "Finance"

    def test_json_with_markdown_fences(self, finance_plan):
        raw = "```json\n" + json.dumps(finance_plan) + "\n```"
        is_valid, plan, errors = parse_and_validate(raw)
        assert is_valid

    def test_broken_json(self):
        is_valid, plan, errors = parse_and_validate("{broken json")
        assert not is_valid
        assert plan is None
        assert any("parse error" in e.lower() for e in errors)

    def test_truncated_json_recovered(self):
        """Truncated JSON (e.g. from max_tokens cutoff) should be repaired."""
        truncated = '{"domain":"AML","intent":"Find structuring","dataset":"transactions","metrics":["STRUCTURING_FLAG"],"filters":[{"field":"cash","op":"=","value":true}],"group_by":["customer_id"],"post_processing":{"window_days":7,"min_coun'
        is_valid, plan, errors = parse_and_validate(truncated)
        # Should recover enough to parse the outer object
        assert plan is not None, f"Truncated JSON was not recovered: {errors}"
        assert plan["domain"] == "AML"


class TestBuildErrorPlan:
    """Test error plan builder."""

    def test_error_plan_conforms(self):
        plan = build_error_plan(
            domain="Risk",
            dataset="loans",
            error_type="unsupported_request",
            message="Not supported",
            repair_attempted=False,
        )
        is_valid, errors = validate_query_plan(plan)
        assert is_valid, f"Error plan invalid: {errors}"
        assert plan["intent"] == "error"
        assert plan["error"]["type"] == "unsupported_request"
