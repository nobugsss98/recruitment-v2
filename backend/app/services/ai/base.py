from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class AIProviderError(RuntimeError):
    """Base error raised by provider-neutral text AI services."""


class AIConfigurationError(AIProviderError):
    """Raised when required provider configuration is missing or invalid."""


class AIResponseError(AIProviderError):
    """Raised when a provider response is empty or fails schema validation."""


@runtime_checkable
class TextAIProvider(Protocol):
    def generate_text(
        self,
        *,
        system_instruction: str,
        user_content: str,
    ) -> str:
        """Return generated text for one stateless prompt."""

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[ResponseModel],
    ) -> ResponseModel:
        """Return output parsed and validated into the requested model."""