"""
CoordinatorAgent — the top-level orchestrator.
Routes user prompts through the specialist agent pipeline and merges
outputs into the final response object.

Uses Microsoft Agent Framework patterns for multi-agent orchestration.
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import AgentMessage, BaseAgent
from agents.ontology_agent import FinancialOntologyAgent
from agents.planner_agent import QueryPlannerAgent
from agents.generator_agent import QueryPlanGeneratorAgent
from agents.output_controller_agent import OutputControllerAgent
from agents.executor_agent import ExecutorAgent
from agents.explainer_agent import ExplainerAgent


class CoordinatorAgent(BaseAgent):
    name = "CoordinatorAgent"
    description = "Top-level orchestrator: routes prompt through specialist agents."

    def __init__(self):
        super().__init__()
        self.ontology = FinancialOntologyAgent()
        self.planner = QueryPlannerAgent()
        self.generator = QueryPlanGeneratorAgent()
        self.controller = OutputControllerAgent()
        self.executor = ExecutorAgent()
        self.explainer = ExplainerAgent()

    async def run(self, message: AgentMessage) -> AgentMessage:
        """
        Full pipeline:
        1. OntologyAgent — classify domain + identify metrics
        2. PlannerAgent — build plan skeleton (deterministic)
        3. GeneratorAgent — use model to produce full JSON QueryPlan
        4. OutputControllerAgent — validate + repair loop
        5. ExecutorAgent — run plan over local data
        6. ExplainerAgent — produce human-readable explanation
        """
        trace: list[str] = []

        # 1. Ontology
        ont_msg = await self.ontology.run(message)
        trace.append(f"[Ontology] {ont_msg.content}")

        # 2. Planner
        planner_input = AgentMessage(
            role="agent",
            content=message.content,
            data=ont_msg.data,
        )
        planner_msg = await self.planner.run(planner_input)
        trace.append(f"[Planner] {planner_msg.content}")

        # 3. Generator (model call)
        gen_input = AgentMessage(
            role="agent",
            content=message.content,
            data=planner_msg.data,
        )
        gen_msg = await self.generator.run(gen_input)
        trace.append(f"[Generator] produced raw output ({len(gen_msg.content)} chars)")

        # 4. Output Controller (validate + repair)
        ctrl_input = AgentMessage(
            role="agent",
            content=gen_msg.content,
            data=gen_msg.data,
        )
        ctrl_msg = await self.controller.run(ctrl_input)
        retries = ctrl_msg.data.get("retries", 0)
        trace.append(f"[Controller] valid={len(ctrl_msg.data.get('validation_errors', [])) == 0}, retries={retries}")

        query_plan = ctrl_msg.data.get("query_plan", {})

        # 5. Executor
        exec_input = AgentMessage(
            role="agent",
            content="Execute",
            data={"query_plan": query_plan},
        )
        exec_msg = await self.executor.run(exec_input)
        execution_result = exec_msg.data.get("execution_result", {})
        trace.append(f"[Executor] {len(execution_result.get('results', []))} results")

        # 6. Explainer
        explain_input = AgentMessage(
            role="agent",
            content="Explain",
            data={
                "query_plan": query_plan,
                "execution_result": execution_result,
            },
        )
        explain_msg = await self.explainer.run(explain_input)
        explanation = explain_msg.data.get("explanation", "")
        trace.append(f"[Explainer] {len(explanation)} chars")

        # Merge final response
        final_response = {
            "query_plan": query_plan,
            "explanation": explanation,
            "results": execution_result.get("results", []),
            "summary": execution_result.get("summary", {}),
            "safety_notes": execution_result.get("safety_notes", []),
            "agent_trace": trace,
        }

        return AgentMessage(
            role="agent",
            content=json.dumps(final_response, indent=2, default=str),
            data=final_response,
            source_agent=self.name,
        )


async def process_prompt(prompt: str, domain_hint: str | None = None) -> dict[str, Any]:
    """
    Convenience function: run a user prompt through the full agent pipeline.
    Returns the final response dict.
    """
    coordinator = CoordinatorAgent()
    user_msg = AgentMessage(role="user", content=prompt)
    if domain_hint and domain_hint != "Auto":
        user_msg.data["domain_hint"] = domain_hint
    result = await coordinator.run(user_msg)
    return result.data
