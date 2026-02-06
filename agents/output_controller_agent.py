"""
OutputControllerAgent — validates the QueryPlan JSON against the schema.
If invalid, crafts a repair prompt and retries up to MAX_RETRIES times.
If still invalid, returns a structured error object that conforms to the schema.
"""

from __future__ import annotations

import json

from agents.base import AgentMessage, BaseAgent
from core.foundry_client import chat_completion
from core.schema_validate import (
    build_error_plan,
    get_schema,
    parse_and_validate,
    validate_query_plan,
)

MAX_RETRIES = 2

_REPAIR_SYSTEM = """You are a JSON repair assistant. The following JSON was supposed to conform
to the QueryPlan schema but has validation errors. Fix the JSON so it conforms.
Output ONLY the corrected JSON object — nothing else.

Schema:
{schema}
"""


class OutputControllerAgent(BaseAgent):
    name = "OutputControllerAgent"
    description = "Validates QueryPlan JSON against schema; runs repair loop on failure."

    async def run(self, message: AgentMessage) -> AgentMessage:
        raw_text = message.data.get("raw_plan_text", message.content)
        prompt_text = message.data.get("prompt_text", "")

        is_valid, plan, errors = parse_and_validate(raw_text)

        if is_valid and plan is not None:
            return AgentMessage(
                role="agent",
                content="QueryPlan validated successfully.",
                data={"query_plan": plan, "validation_errors": [], "retries": 0},
                source_agent=self.name,
            )

        # --- Repair loop ---
        schema_str = json.dumps(get_schema(), indent=2)
        current_text = raw_text
        current_errors = errors

        for attempt in range(1, MAX_RETRIES + 1):
            repair_prompt = (
                f"Original JSON (invalid):\n{current_text}\n\n"
                f"Validation errors:\n" + "\n".join(current_errors) + "\n\n"
                f"Fix the JSON. Output ONLY the corrected JSON object."
            )
            messages = [
                {"role": "system", "content": _REPAIR_SYSTEM.format(schema=schema_str)},
                {"role": "user", "content": repair_prompt},
            ]
            repaired_text = chat_completion(messages, temperature=0.0, max_tokens=2048)
            is_valid, plan, new_errors = parse_and_validate(repaired_text)

            if is_valid and plan is not None:
                return AgentMessage(
                    role="agent",
                    content=f"QueryPlan repaired on attempt {attempt}.",
                    data={
                        "query_plan": plan,
                        "validation_errors": [],
                        "retries": attempt,
                    },
                    source_agent=self.name,
                )

            current_text = repaired_text
            current_errors = new_errors

        # --- All retries exhausted: return schema-valid error object ---
        error_plan = build_error_plan(
            domain=_extract_field(raw_text, "domain", "Finance"),
            dataset=_extract_field(raw_text, "dataset", "interest"),
            error_type="validation_error",
            message=f"Failed to produce valid QueryPlan after {MAX_RETRIES} retries. Errors: {'; '.join(current_errors[:3])}",
            repair_attempted=True,
        )

        return AgentMessage(
            role="agent",
            content="QueryPlan validation failed; returning error object.",
            data={
                "query_plan": error_plan,
                "validation_errors": current_errors,
                "retries": MAX_RETRIES,
            },
            source_agent=self.name,
        )


def _extract_field(text: str, field: str, default: str) -> str:
    """Try to extract a field value from possibly malformed JSON text."""
    try:
        obj = json.loads(text)
        return obj.get(field, default)
    except Exception:
        return default
