"""Custom domain exception types."""

from __future__ import annotations


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class EntityNotFoundError(DomainException):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity: str, entity_id: str) -> None:
        super().__init__(
            message=f"{entity} with id '{entity_id}' not found.",
            code="NOT_FOUND",
        )
        self.entity = entity
        self.entity_id = entity_id


class ValidationDomainError(DomainException):
    """Raised when domain validation rules are violated."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="VALIDATION_ERROR")


class LLMProviderError(DomainException):
    """Raised when the LLM provider fails."""

    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(
            message=f"LLM provider '{provider}' error: {detail}",
            code="LLM_ERROR",
        )
        self.provider = provider
