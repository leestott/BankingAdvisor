"""
ExplainerAgent — produces human-readable explanation from QueryPlan + execution results.
Uses the local model to generate natural language; falls back to template if model unavailable.
"""

from __future__ import annotations

import json

from agents.base import AgentMessage, BaseAgent
from agents.ontology_agent import ONTOLOGY
from core.foundry_client import chat_completion, MOCK_MODE


_SYSTEM_PROMPT = """You are a banking analytics explanation assistant.
Given a query plan and its execution results, produce a clear, concise explanation.
Include:
1. What was asked
2. Key terms and their definitions
3. Assumptions made
4. Safety notes (if any)
Keep it under 300 words. Do NOT output JSON."""


class ExplainerAgent(BaseAgent):
    name = "ExplainerAgent"
    description = "Produces human-readable explanation from QueryPlan and results."

    async def run(self, message: AgentMessage) -> AgentMessage:
        plan = message.data.get("query_plan", {})
        result = message.data.get("execution_result", {})
        safety_notes = result.get("safety_notes", [])

        # If error plan, return error explanation
        if plan.get("intent") == "error":
            error_msg = plan.get("error", {}).get("message", "Unknown error")
            explanation = f"**Error:** {error_msg}\n\nThe system was unable to produce a valid query plan."
            return AgentMessage(
                role="agent",
                content=explanation,
                data={"explanation": explanation, "safety_notes": []},
                source_agent=self.name,
            )

        # Try model-generated explanation
        if not MOCK_MODE:
            try:
                explanation = self._model_explanation(plan, result)
                return AgentMessage(
                    role="agent",
                    content=explanation,
                    data={"explanation": explanation, "safety_notes": safety_notes},
                    source_agent=self.name,
                )
            except Exception:
                pass  # Fall back to template

        # Template-based explanation (mock mode or model failure)
        explanation = self._template_explanation(plan, result)
        return AgentMessage(
            role="agent",
            content=explanation,
            data={"explanation": explanation, "safety_notes": safety_notes},
            source_agent=self.name,
        )

    def _model_explanation(self, plan: dict, result: dict) -> str:
        summary_str = json.dumps(result.get("summary", {}), indent=2)
        safety = result.get("safety_notes", [])
        num_results = len(result.get("results", []))

        user_msg = (
            f"Query Plan:\n{json.dumps(plan, indent=2)}\n\n"
            f"Summary: {summary_str}\n"
            f"Number of result rows: {num_results}\n"
            f"Safety notes: {json.dumps(safety)}\n\n"
            f"Produce a clear explanation."
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return chat_completion(messages, temperature=0.3, max_tokens=500)

    def _template_explanation(self, plan: dict, result: dict) -> str:
        """Simple template-based explanation."""
        domain = plan.get("domain", "Unknown")
        intent = plan.get("intent", "")
        metrics = plan.get("metrics", [])
        dataset = plan.get("dataset", "")
        summary = result.get("summary", {})
        safety = result.get("safety_notes", [])
        num_results = len(result.get("results", []))

        lines = [
            f"## {domain} Analysis",
            "",
            f"**Intent:** {intent}",
            f"**Dataset:** {dataset}",
            f"**Metrics computed:** {', '.join(metrics)}",
            f"**Results returned:** {num_results} rows",
            "",
        ]

        # Term definitions
        if plan.get("explanation_requirements", {}).get("include_terms_used", False):
            lines.append("### Terms Used")
            for m in metrics:
                if m in ONTOLOGY:
                    info = ONTOLOGY[m]
                    lines.append(f"- **{info['label']}** ({m}): {info['formula']}")
            lines.append("")

        # Assumptions
        if plan.get("explanation_requirements", {}).get("include_assumptions", False):
            lines.append("### Assumptions")
            filters = plan.get("filters", [])
            time_range = plan.get("time_range")
            if filters:
                lines.append(f"- Filters applied: {len(filters)} condition(s)")
                for f in filters:
                    lines.append(f"  - {f['field']} {f['op']} {f['value']}")
            if time_range:
                lines.append(f"- Time range: {time_range['start']} to {time_range['end']}")
            else:
                lines.append("- No time range filter applied (all available data used)")
            lines.append("")

        # Summary
        if summary:
            lines.append("### Summary")
            for k, v in summary.items():
                lines.append(f"- {k}: {v}")
            lines.append("")

        # Safety notes
        if safety and plan.get("explanation_requirements", {}).get("include_safety_notes", False):
            lines.append("### Safety Notes")
            for note in safety:
                lines.append(f"- ⚠ {note}")

        return "\n".join(lines)
