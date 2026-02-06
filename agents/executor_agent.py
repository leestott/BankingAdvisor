"""
ExecutorAgent — deterministic Python execution over JSON files.
NO model calls. Delegates to core.executor.
"""

from __future__ import annotations

from agents.base import AgentMessage, BaseAgent
from core.executor import execute_query_plan


class ExecutorAgent(BaseAgent):
    name = "ExecutorAgent"
    description = "Executes a validated QueryPlan deterministically over local JSON data."

    async def run(self, message: AgentMessage) -> AgentMessage:
        plan = message.data.get("query_plan", {})

        try:
            result = execute_query_plan(plan)
        except Exception as exc:
            result = {
                "results": [],
                "summary": {"error": f"Execution error: {exc}"},
                "safety_notes": [str(exc)],
            }

        return AgentMessage(
            role="agent",
            content="Execution complete.",
            data={
                "query_plan": plan,
                "execution_result": result,
            },
            source_agent=self.name,
        )
