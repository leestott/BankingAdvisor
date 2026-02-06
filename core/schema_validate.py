"""
JSON Schema validation and repair utilities for QueryPlan objects.
"""

import json
import os
from pathlib import Path

import jsonschema

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "query_plan.schema.json"


def load_schema() -> dict:
    """Load the QueryPlan JSON Schema from disk."""
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_SCHEMA_CACHE: dict | None = None


def get_schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = load_schema()
    return _SCHEMA_CACHE


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_query_plan(plan: dict) -> tuple[bool, list[str]]:
    """
    Validate a QueryPlan dict against the schema.
    Returns (is_valid, list_of_error_messages).
    """
    schema = get_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(plan), key=lambda e: list(e.absolute_path))
    if not errors:
        return True, []
    messages = []
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        messages.append(f"{path}: {err.message}")
    return False, messages


def parse_and_validate(raw_text: str) -> tuple[bool, dict | None, list[str]]:
    """
    Parse raw text as JSON, then validate against schema.
    Returns (is_valid, parsed_dict_or_None, error_messages).
    """
    # Try to extract JSON from possible markdown fences
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        plan = json.loads(text)
    except json.JSONDecodeError as exc:
        # Attempt to recover truncated JSON by closing open braces/brackets
        repaired = _try_repair_truncated_json(text)
        if repaired is not None:
            plan = repaired
        else:
            return False, None, [f"JSON parse error: {exc}"]

    if not isinstance(plan, dict):
        return False, None, ["Expected a JSON object, got " + type(plan).__name__]

    is_valid, errors = validate_query_plan(plan)
    return is_valid, plan, errors


# ---------------------------------------------------------------------------
# Truncated JSON recovery
# ---------------------------------------------------------------------------

def _try_repair_truncated_json(text: str) -> dict | None:
    """
    Attempt to repair JSON that was truncated mid-output by the model.
    Strategy: strip trailing incomplete value, then close open braces/brackets.
    """
    import re as _re

    s = text.rstrip()
    # Strip trailing incomplete string literal (unterminated quote)
    s = _re.sub(r',?\s*"[^"]*$', '', s)
    # Strip trailing incomplete key-value pair
    s = _re.sub(r',?\s*"[^"]*"\s*:\s*$', '', s)
    # Strip dangling comma
    s = s.rstrip().rstrip(',')

    # Count open/close braces and brackets
    open_braces = s.count('{') - s.count('}')
    open_brackets = s.count('[') - s.count(']')

    # Close them in reverse order of likely nesting
    s += ']' * max(open_brackets, 0)
    s += '}' * max(open_braces, 0)

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return None


# ---------------------------------------------------------------------------
# Error / refusal object builder
# ---------------------------------------------------------------------------

def build_error_plan(
    domain: str = "Finance",
    dataset: str = "interest",
    error_type: str = "validation_error",
    message: str = "Unable to produce a valid query plan.",
    repair_attempted: bool = True,
) -> dict:
    """Build a schema-valid error/refusal QueryPlan object."""
    return {
        "domain": domain,
        "intent": "error",
        "dataset": dataset,
        "error": {
            "type": error_type,
            "message": message,
            "repair_attempted": repair_attempted,
        },
    }
