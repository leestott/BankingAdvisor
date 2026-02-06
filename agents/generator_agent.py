"""
QueryPlanGeneratorAgent — uses Foundry Local model to generate the final
JSON QueryPlan. Instructs the model to output ONLY valid JSON per schema.
"""

from __future__ import annotations

import json

from agents.base import AgentMessage, BaseAgent
from core.foundry_client import chat_completion
from core.schema_validate import get_schema


_SYSTEM_PROMPT = """You are a banking analytics query planner.
You MUST output ONLY a single valid JSON object conforming to the provided JSON Schema.
Do NOT output any text, markdown, or explanation — ONLY the JSON object.
Do NOT output any form of query language or code — ONLY JSON.

JSON Schema:
{schema}

Guidelines:
- domain must be one of: Finance, Risk, Treasury, AML
- dataset must be one of: interest, loans, liquidity, transactions
- metrics must be from: NII, NIM, ECL, NSFR, STRUCTURING_FLAG
- filters use field/op/value where op is one of: =, !=, >, <, >=, <=, in, contains
- All date strings must be YYYY-MM-DD format
- If you cannot answer, set intent to "error" and include error object
"""


class QueryPlanGeneratorAgent(BaseAgent):
    name = "QueryPlanGeneratorAgent"
    description = "Uses Foundry Local model to generate a JSON QueryPlan."

    async def run(self, message: AgentMessage) -> AgentMessage:
        skeleton = message.data.get("plan_skeleton", {})
        prompt_text = message.data.get("prompt_text", message.content)

        schema_str = json.dumps(get_schema(), indent=2)
        system_msg = _SYSTEM_PROMPT.format(schema=schema_str)

        user_msg = (
            f"User prompt: {prompt_text}\n\n"
            f"A helpful assistant has already analysed the prompt and produced this "
            f"partial plan skeleton. Use it as guidance but output a complete, "
            f"schema-valid JSON QueryPlan object. Be concise — output ONLY the "
            f"JSON with no extra whitespace or comments:\n\n"
            f"{json.dumps(skeleton, separators=(',', ':'))}"
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        raw_output = chat_completion(messages, temperature=0.1, max_tokens=2048)

        return AgentMessage(
            role="agent",
            content=raw_output,
            data={"raw_plan_text": raw_output, "prompt_text": prompt_text},
            source_agent=self.name,
        )
