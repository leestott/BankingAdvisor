"""
FinancialOntologyAgent — maps natural-language financial terms to canonical
metric names and definitions used downstream by the QueryPlannerAgent.
No LLM calls; this is a deterministic lookup agent.
"""

from __future__ import annotations

from agents.base import AgentMessage, BaseAgent

# ---------------------------------------------------------------------------
# Ontology / metric dictionary
# ---------------------------------------------------------------------------
ONTOLOGY: dict[str, dict] = {
    "NII": {
        "canonical": "NII",
        "label": "Net Interest Income",
        "formula": "interest_income - interest_expense",
        "dataset": "interest",
        "keywords": ["net interest income", "nii", "interest margin income"],
    },
    "NIM": {
        "canonical": "NIM",
        "label": "Net Interest Margin",
        "formula": "NII / avg_earning_assets",
        "dataset": "interest",
        "keywords": ["net interest margin", "nim", "margin"],
    },
    "ECL": {
        "canonical": "ECL",
        "label": "Expected Credit Loss",
        "formula": "PD × LGD × EAD",
        "dataset": "loans",
        "keywords": ["expected credit loss", "ecl", "credit loss", "ifrs 9", "ifrs9", "stage migration"],
    },
    "NSFR": {
        "canonical": "NSFR",
        "label": "Net Stable Funding Ratio",
        "formula": "available_stable_funding / required_stable_funding",
        "dataset": "liquidity",
        "keywords": ["nsfr", "net stable funding", "stable funding ratio", "liquidity ratio"],
    },
    "STRUCTURING_FLAG": {
        "canonical": "STRUCTURING_FLAG",
        "label": "Structuring / Smurfing Detection",
        "formula": "Heuristic: cash deposits near threshold, count >= N in sliding window",
        "dataset": "transactions",
        "keywords": [
            "structuring", "smurfing", "cash deposit", "reporting threshold",
            "aml", "anti-money laundering", "suspicious", "below threshold",
        ],
    },
}

# Domain classification keywords
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "Finance": ["interest", "nim", "nii", "margin", "income", "expense", "earning", "product"],
    "Risk": ["ecl", "credit loss", "ifrs", "stage", "migration", "pd", "lgd", "ead", "impairment"],
    "Treasury": ["nsfr", "liquidity", "stable funding", "treasury", "funding ratio"],
    "AML": ["aml", "structuring", "smurfing", "cash deposit", "threshold", "suspicious", "money laundering"],
}


def classify_domain(text: str) -> str:
    """Classify prompt text into a banking domain."""
    lower = text.lower()
    scores: dict[str, int] = {d: 0 for d in DOMAIN_KEYWORDS}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[domain] += 1
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "Finance"


def identify_metrics(text: str) -> list[str]:
    """Identify which canonical metrics are relevant to the prompt."""
    lower = text.lower()
    found = []
    for metric_id, info in ONTOLOGY.items():
        for kw in info["keywords"]:
            if kw in lower:
                found.append(metric_id)
                break
    return found if found else ["NII", "NIM"]  # default


def get_definitions(metrics: list[str]) -> list[dict]:
    """Return definitions for the identified metrics."""
    return [ONTOLOGY[m] for m in metrics if m in ONTOLOGY]


class FinancialOntologyAgent(BaseAgent):
    name = "FinancialOntologyAgent"
    description = "Maps prompt terms to canonical metrics and domain classification."

    async def run(self, message: AgentMessage) -> AgentMessage:
        prompt_text = message.content
        domain = classify_domain(prompt_text)
        metrics = identify_metrics(prompt_text)
        definitions = get_definitions(metrics)
        dataset = definitions[0]["dataset"] if definitions else "interest"

        return AgentMessage(
            role="agent",
            content=f"Domain: {domain}, Metrics: {metrics}",
            data={
                "domain": domain,
                "metrics": metrics,
                "definitions": definitions,
                "dataset": dataset,
            },
            source_agent=self.name,
        )
