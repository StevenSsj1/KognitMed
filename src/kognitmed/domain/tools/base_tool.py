"""Abstract base class for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    Base class for all KognitMed agent tools.

    To add a new tool, subclass this and implement `name`, `description`, and `execute`.
    Tools should be pure functions with no side effects where possible.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (e.g., 'drug_interaction_checker')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description shown to the LLM for tool selection."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with the given arguments."""
        ...

    def to_schema(self) -> dict[str, Any]:
        """Return OpenAI-compatible tool schema for function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }
