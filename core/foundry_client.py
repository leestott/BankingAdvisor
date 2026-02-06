"""
Foundry Local client wrapper.
Talks to the local OpenAI-compatible endpoint provided by Foundry Local.
Falls back to mock mode for testing when MOCK_MODE=1 or the endpoint is unreachable.
"""

import json
import os
import re
import subprocess
import urllib.request
from typing import Optional

import openai


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FOUNDRY_API_KEY = os.getenv("FOUNDRY_LOCAL_API_KEY", "foundry-local")  # placeholder
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5-0.5b")
MOCK_MODE = os.getenv("MOCK_MODE", "0") == "1"

# Low temperature for structured output reliability
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 1024


# ---------------------------------------------------------------------------
# Dynamic endpoint discovery
# ---------------------------------------------------------------------------

def _discover_foundry_endpoint() -> str | None:
    """
    Discover the Foundry Local service endpoint dynamically.

    Strategy:
      1. Use FOUNDRY_LOCAL_ENDPOINT env var if set explicitly.
      2. Query `foundry service status` CLI for the running URL.
      3. Probe the discovered URL's /openai/status to confirm it's live.

    Returns the base URL (e.g. "http://127.0.0.1:65026/v1") or None.
    """
    # 1. Explicit env var override
    explicit = os.getenv("FOUNDRY_LOCAL_ENDPOINT")
    if explicit:
        return explicit

    # 2. Ask the CLI for the management URL
    try:
        out = subprocess.check_output(
            ["foundry", "service", "status"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        match = re.search(r"http://[\d.]+:\d+", out)
        if match:
            base = match.group(0)  # e.g. "http://127.0.0.1:65026"
            # 3. Verify the endpoint is actually responding
            try:
                urllib.request.urlopen(f"{base}/openai/status", timeout=2)
                return f"{base}/v1"
            except Exception:
                pass
    except Exception:
        pass

    return None


# Cache the discovered endpoint and resolved model ID for the process lifetime
_FOUNDRY_ENDPOINT: str | None = None
_RESOLVED_MODEL_ID: str | None = None


def _get_endpoint() -> str | None:
    """Return the cached Foundry endpoint, discovering it on first call."""
    global _FOUNDRY_ENDPOINT
    if _FOUNDRY_ENDPOINT is None:
        _FOUNDRY_ENDPOINT = _discover_foundry_endpoint() or ""
    return _FOUNDRY_ENDPOINT or None


def _resolve_model_id() -> str:
    """
    Resolve the configured MODEL_NAME alias to the full model ID that
    Foundry Local expects for inference (e.g. 'qwen2.5-0.5b' →
    'qwen2.5-0.5b-instruct-cuda-gpu:4').

    Falls back to MODEL_NAME if resolution fails.
    """
    global _RESOLVED_MODEL_ID
    if _RESOLVED_MODEL_ID is not None:
        return _RESOLVED_MODEL_ID

    try:
        client = _build_client()
        if client is None:
            _RESOLVED_MODEL_ID = MODEL_NAME
            return _RESOLVED_MODEL_ID
        models = client.models.list()
        for m in models.data:
            mid = m.id  # type: ignore[union-attr]
            if mid == MODEL_NAME or mid.lower().startswith(MODEL_NAME.lower()):
                _RESOLVED_MODEL_ID = mid
                return _RESOLVED_MODEL_ID
        # No match — use first loaded model, or fall back to alias
        if models.data:
            _RESOLVED_MODEL_ID = models.data[0].id  # type: ignore[union-attr]
        else:
            _RESOLVED_MODEL_ID = MODEL_NAME
    except Exception:
        _RESOLVED_MODEL_ID = MODEL_NAME

    return _RESOLVED_MODEL_ID


def _build_client() -> openai.OpenAI | None:
    """Return an OpenAI client pointed at Foundry Local, or None if unavailable."""
    endpoint = _get_endpoint()
    if not endpoint:
        return None
    return openai.OpenAI(
        base_url=endpoint,
        api_key=FOUNDRY_API_KEY,
    )


# ---------------------------------------------------------------------------
# Model info helpers
# ---------------------------------------------------------------------------

def _parse_device_from_model_id(model_id: str) -> str:
    """Extract device type (CPU / CUDA GPU / GPU / NPU) from a Foundry model ID."""
    mid = model_id.lower()
    if "npu" in mid:
        return "NPU"
    if "cuda-gpu" in mid:
        return "CUDA GPU"
    if "gpu" in mid:
        return "GPU"
    if "cpu" in mid:
        return "CPU"
    return "Unknown"


def get_model_info() -> dict:
    """
    Query Foundry Local for loaded model details.

    Returns a dict with:
        alias      – short model alias (e.g. "qwen2.5-0.5b")
        model_id   – full model identifier reported by the endpoint (or "")
        device     – inferred device type (CPU / GPU / CUDA GPU / NPU) (or "")
        endpoint   – the resolved endpoint URL (or "")
        connected  – True if Foundry Local responded with model data
    """
    alias = MODEL_NAME
    info: dict = {
        "alias": alias,
        "model_id": "",
        "device": "",
        "endpoint": "",
        "connected": False,
    }

    if MOCK_MODE:
        return info

    endpoint = _get_endpoint()
    if not endpoint:
        return info

    info["endpoint"] = endpoint

    try:
        client = _build_client()
        if client is None:
            return info
        models = client.models.list()
        # Find the model that matches the configured alias
        for m in models.data:
            mid = m.id  # type: ignore[union-attr]
            # Exact match or alias is a prefix of the model id
            if mid == alias or mid.lower().startswith(alias.lower()):
                info["model_id"] = mid
                info["device"] = _parse_device_from_model_id(mid)
                info["connected"] = True
                return info
        # If no prefix match, return first model if available
        if models.data:
            first = models.data[0]
            info["model_id"] = first.id  # type: ignore[union-attr]
            info["device"] = _parse_device_from_model_id(first.id)  # type: ignore[union-attr]
            info["connected"] = True
    except Exception:
        pass  # endpoint unreachable — stay with defaults

    return info


# ---------------------------------------------------------------------------
# Mock fixtures (used when MOCK_MODE=1 or endpoint unreachable)
# ---------------------------------------------------------------------------
_MOCK_FIXTURES: dict[str, dict] = {
    "Finance": {
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
    },
    "Risk": {
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
    },
    "Treasury": {
        "domain": "Treasury",
        "intent": "Show monthly NSFR trend and flag months below 100%",
        "dataset": "liquidity",
        "filters": [{"field": "region", "op": "=", "value": "UK"}],
        "group_by": ["month"],
        "metrics": ["NSFR"],
        "post_processing": {"flag_threshold": 100.0, "sort_by": "month", "sort_order": "asc"},
        "explanation_requirements": {
            "include_terms_used": True,
            "include_assumptions": True,
            "include_safety_notes": True,
        },
    },
    "AML": {
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
    },
}


def get_mock_plan(domain: str) -> dict:
    """Return a deterministic mock QueryPlan for the given domain."""
    return _MOCK_FIXTURES.get(domain, _MOCK_FIXTURES["Finance"])


# ---------------------------------------------------------------------------
# Chat completion wrapper
# ---------------------------------------------------------------------------

def chat_completion(
    messages: list[dict],
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    model: Optional[str] = None,
) -> str:
    """
    Send a chat completion request to Foundry Local (or return mock).
    Returns the raw assistant content string.
    """
    if MOCK_MODE:
        # In mock mode, try to infer domain from messages and return fixture
        domain = _infer_domain_from_messages(messages)
        return json.dumps(get_mock_plan(domain))

    client = _build_client()
    if client is None:
        # No endpoint discovered — fall back to mock
        print("[FoundryClient] No Foundry Local endpoint found, falling back to mock mode.")
        domain = _infer_domain_from_messages(messages)
        return json.dumps(get_mock_plan(domain))

    resolved = model or _resolve_model_id()
    try:
        response = client.chat.completions.create(
            model=resolved,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        # Fallback to mock if endpoint is unreachable
        print(f"[FoundryClient] Endpoint unreachable ({exc}), falling back to mock mode.")
        domain = _infer_domain_from_messages(messages)
        return json.dumps(get_mock_plan(domain))


def _infer_domain_from_messages(messages: list[dict]) -> str:
    """Simple keyword heuristic to pick a mock fixture domain."""
    text = " ".join(m.get("content", "") for m in messages).lower()
    if any(kw in text for kw in ["aml", "structur", "smurfing", "threshold", "cash deposit"]):
        return "AML"
    if any(kw in text for kw in ["nsfr", "liquidity", "stable funding", "treasury"]):
        return "Treasury"
    if any(kw in text for kw in ["ecl", "ifrs", "stage", "migration", "credit loss"]):
        return "Risk"
    return "Finance"
