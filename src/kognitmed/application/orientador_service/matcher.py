"""Backward-compatible aliases for reasoning/matcher layer.

Canonical implementation lives in:
- kognitmed.application.orientador_service.agents.reasoning_agent
"""

from kognitmed.application.orientador_service.agents.reasoning_agent import MatchResult, ReasoningAgent

# Legacy name kept for compatibility with existing imports
MatcherLayer = ReasoningAgent

__all__ = ["ReasoningAgent", "MatcherLayer", "MatchResult"]
