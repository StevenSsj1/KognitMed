"""Backward-compatible aliases for intake layer.

Canonical implementation lives in:
- kognitmed.application.orientador_service.agents.intake_agent
"""

from kognitmed.application.orientador_service.agents.intake_agent import IntakeAgent, IntakeResult

# Legacy names kept for compatibility with existing imports
IntakeLayer = IntakeAgent

__all__ = ["IntakeAgent", "IntakeLayer", "IntakeResult"]
