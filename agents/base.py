"""
Base agent class for the banking query copilot.
Uses Microsoft Agent Framework (microsoft-agent-framework) for orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    """A simple message envelope passed between agents."""
    role: str  # "user", "agent", "system"
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    source_agent: str = ""


class BaseAgent:
    """
    Lightweight base class wrapping Microsoft Agent Framework patterns.
    Each agent implements `run(message) -> AgentMessage`.
    """

    name: str = "BaseAgent"
    description: str = ""

    def __init__(self, name: str | None = None):
        if name:
            self.name = name

    async def run(self, message: AgentMessage) -> AgentMessage:
        """Override in subclass."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
