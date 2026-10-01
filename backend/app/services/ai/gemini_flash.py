from typing import Any, TypeVar
import time

from google import genai
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import settings
from app.services.ai.base import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
)
from app.utils.logging import get_logger


_logger = get_logger("app.ai")


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class GeminiFlashProvider:
    def __init__(
        self,
        *,
        api_key: str | SecretStr | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        selected_model = settings.gemini_model if model is None else model
        if not isinstance(selected_model, str) or not selected_model.strip():
            raise AIConfigurationError("Gemini model configuration is invalid")
        self._model = selected_model.strip()

        if client is not None:
            self._client = client
            return

        selected_key = settings.gemini_api_key if api_key is None else api_key
        if isinstance(selected_key, SecretStr):
            selected_key = selected_key.get_secret_value()
        if not isinstance(selected_key, str) or not selected_key.strip():
            raise AIConfigurationError("GEMINI_API_KEY is required for Gemini calls")

        try:
            self._client = genai.Client(api_key=selected_key.strip())
        except Exception as error:
            raise AIConfigurationError("Gemini client configuration failed") from error

    def generate_text(
        self,
        *,
        system_instruction: str,
        user_content: str,
    ) -> str:
        interaction = self._create_interaction(
            system_instruction=system_instruction,
            user_content=user_content,
        )
        return self._read_output_text(interaction)

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[ResponseModel],
    ) -> ResponseModel:
        response_format = {
            "type": "text",
            "mime_type": "application/json",
            "schema": response_model.model_json_schema(),
        }
        interaction = self._create_interaction(
            system_instruction=system_instruction,
            user_content=user_content,
            response_format=response_format,
        )
        output_text = self._read_output_text(interaction)

        try:
            return response_model.model_validate_json(output_text)
        except (ValidationError, ValueError, TypeError) as error:
            raise AIResponseError(
                "Gemini structured response did not match the requested schema"
            ) from error

    def _create_interaction(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_format: dict[str, object] | None = None,
    ) -> Any:
        if not isinstance(system_instruction, str) or not system_instruction.strip():
            raise ValueError("system_instruction must be a non-empty string")
        if not isinstance(user_content, str) or not user_content.strip():
            raise ValueError("user_content must be a non-empty string")

        request: dict[str, object] = {
            "model": self._model,
            "system_instruction": system_instruction,
            "input": user_content,
            "store": False,
        }
        if response_format is not None:
            request["response_format"] = response_format

        try:
            start = time.perf_counter()
            interaction = self._client.interactions.create(**request)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
        except Exception as error:
            _logger.warning(
                "ai request failed",
                model=self._model,
                structured=response_format is not None,
                error=type(error).__name__,
            )
            raise AIProviderError("Gemini request failed") from error
        _logger.info(
            "ai request completed",
            model=self._model,
            structured=response_format is not None,
            latency_ms=latency_ms,
        )
        return interaction

    @staticmethod
    def _read_output_text(interaction: Any) -> str:
        output_text = getattr(interaction, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise AIResponseError("Gemini returned an empty or non-text response")
        return output_text.strip()