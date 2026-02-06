"""
test_repair.py — validate the repair loop in OutputControllerAgent.
Feeds malformed JSON and ensures a schema-valid error object is returned.
"""

import asyncio
import json
import os
import sys

import pytest

os.environ["MOCK_MODE"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.base import AgentMessage
from agents.output_controller_agent import OutputControllerAgent
from core.schema_validate import validate_query_plan


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestRepairLoop:
    """Test OutputControllerAgent repair behaviour."""

    def test_valid_plan_passes_through(self, finance_plan):
        """A valid plan should not trigger repair."""
        agent = OutputControllerAgent()
        msg = AgentMessage(
            role="agent",
            content=json.dumps(finance_plan),
            data={"raw_plan_text": json.dumps(finance_plan)},
        )
        result = _run(agent.run(msg))
        assert result.data["retries"] == 0
        assert result.data["validation_errors"] == []
        plan = result.data["query_plan"]
        is_valid, _ = validate_query_plan(plan)
        assert is_valid

    def test_malformed_json_triggers_repair(self, malformed_json):
        """Malformed JSON should trigger repair; result should still be schema-valid."""
        agent = OutputControllerAgent()
        msg = AgentMessage(
            role="agent",
            content=malformed_json,
            data={"raw_plan_text": malformed_json},
        )
        result = _run(agent.run(msg))
        plan = result.data["query_plan"]
        is_valid, errors = validate_query_plan(plan)
        assert is_valid, f"Repaired/error plan should be schema-valid: {errors}"

    def test_completely_broken_returns_schema_valid(self):
        """Completely broken text should still produce a schema-valid result.
        In mock mode the repair loop succeeds (mock returns valid fixture).
        In real mode with a failing model, an error object is returned.
        Either way, the output must be schema-valid."""
        agent = OutputControllerAgent()
        msg = AgentMessage(
            role="agent",
            content="this is not json at all !!!",
            data={"raw_plan_text": "this is not json at all !!!"},
        )
        result = _run(agent.run(msg))
        plan = result.data["query_plan"]
        is_valid, errors = validate_query_plan(plan)
        assert is_valid, f"Result plan must be schema-valid: {errors}"

    def test_error_object_when_repair_fails(self):
        """Directly test that build_error_plan produces a valid error object."""
        from core.schema_validate import build_error_plan
        plan = build_error_plan(
            domain="Finance",
            dataset="interest",
            error_type="validation_error",
            message="All repair attempts failed",
            repair_attempted=True,
        )
        is_valid, errors = validate_query_plan(plan)
        assert is_valid, f"Error plan must be schema-valid: {errors}"
        assert plan["intent"] == "error"
        assert plan["error"]["repair_attempted"] is True

    def test_repair_retries_capped(self, malformed_json):
        """Retries should not exceed MAX_RETRIES (2)."""
        agent = OutputControllerAgent()
        msg = AgentMessage(
            role="agent",
            content=malformed_json,
            data={"raw_plan_text": malformed_json},
        )
        result = _run(agent.run(msg))
        assert result.data["retries"] <= 2


class TestEndToEndPipeline:
    """Run the full pipeline in mock mode to verify integration."""

    def test_full_pipeline_finance(self):
        from agents.coordinator_agent import process_prompt

        result = _run(process_prompt(
            "Calculate Net Interest Margin by product for UK in Q1 2025"
        ))
        assert "query_plan" in result
        assert "results" in result
        assert len(result["results"]) > 0
        plan = result["query_plan"]
        is_valid, errors = validate_query_plan(plan)
        assert is_valid, f"Pipeline plan invalid: {errors}"

    def test_full_pipeline_risk(self):
        from agents.coordinator_agent import process_prompt

        result = _run(process_prompt(
            "Show loans that migrated from Stage 1 to Stage 2 in the last 30 days and compute expected credit loss"
        ))
        assert len(result["results"]) > 0

    def test_full_pipeline_treasury(self):
        from agents.coordinator_agent import process_prompt

        result = _run(process_prompt(
            "Show monthly NSFR trend and flag months below 100%"
        ))
        assert len(result["results"]) > 0

    def test_full_pipeline_aml(self):
        from agents.coordinator_agent import process_prompt

        result = _run(process_prompt(
            "Find customers with repeated cash deposits just below reporting thresholds within 7 days"
        ))
        assert len(result["results"]) > 0
        assert any("not a determination" in n.lower() for n in result.get("safety_notes", []))
