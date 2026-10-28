# Google GenAI SDK wrapper (Gemini 2.5 Pro & Flash)
"""
Thin async wrapper around ``google-genai`` providing structured output
generation with automatic Pydantic V2 parsing.

Usage::

    from src.engine.gemini_client import gemini
    result = await gemini.generate_structured(prompt, MyModel)
"""

from __future__ import annotations

import logging
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiClient:
    """
    Async wrapper for the Google GenAI SDK.

    Initialises a single ``genai.Client`` and exposes
    ``generate_structured`` for JSON-schema-constrained generation.
    """

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        *,
        model: str | None = None,
        temperature: float = 0.1,
        system_instruction: str | None = None,
    ) -> T:
        """
        Generate content and parse the response into a Pydantic model.

        Args:
            prompt: The user prompt to send.
            response_schema: Pydantic V2 model class for structured output.
            model: Model name override (defaults to ``settings.gemini_fast_model``).
            temperature: Sampling temperature (default 0.1 for determinism).
            system_instruction: Optional system-level instruction.

        Returns:
            An instance of ``response_schema`` parsed from the model output.

        Raises:
            ValueError: If the response cannot be parsed into the schema.
        """
        model_name = model or settings.gemini_fast_model

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        logger.info(
            "Gemini request: model=%s schema=%s temp=%.2f",
            model_name,
            response_schema.__name__,
            temperature,
        )

        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

        parsed: T = response.parsed  # type: ignore[assignment]

        if parsed is None:
            raise ValueError(
                f"Gemini returned unparseable response for schema "
                f"{response_schema.__name__}. Raw text: {response.text!r}"
            )

        logger.info(
            "Gemini response parsed: model=%s schema=%s",
            model_name,
            response_schema.__name__,
        )

        return parsed


# Module-level singleton
gemini = GeminiClient()
