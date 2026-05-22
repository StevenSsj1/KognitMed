"""Backward-compatible aliases for output layer.

Canonical implementation lives in:
- kognitmed.application.orientador_service.agents.response_agent
"""

from kognitmed.application.orientador_service.agents.response_agent import (
    OutputAgent,
    _EMERGENCY_REPLY,
)

# Legacy name kept for compatibility with existing imports
OutputLayer = OutputAgent

__all__ = ["OutputAgent", "OutputLayer", "_EMERGENCY_REPLY"]
