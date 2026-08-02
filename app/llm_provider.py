"""LLM Provider abstraction.

Defines the interface for text generation backends and implements
a concrete provider for Groq.
"""

import abc
import logging
import os
import time
from typing import Any

import httpx

from .config import LLM_MAX_RETRIES, LLM_MODEL, LLM_TIMEOUT

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised for errors during LLM generation."""


class LLMProvider(abc.ABC):
    """Abstract interface for LLM backends."""

    @abc.abstractmethod
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a response from the LLM given a conversation history.

        Parameters
        ----------
        messages : list[dict[str, str]]
            List of messages (e.g., [{"role": "system", "content": "..."}, ...])

        Returns
        -------
        str
            The generated response string.

        Raises
        ------
        LLMError
            If generation fails.
        """


class GroqProvider(LLMProvider):
    """Concrete provider for the Groq HTTP API."""

    def __init__(self, api_key: str | None = None, model: str = LLM_MODEL):
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise LLMError("GROQ_API_KEY environment variable is not set.")
        
        self._model = model
        self._url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.0,  # Deterministic / factual output
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

        last_err = None
        for attempt in range(LLM_MAX_RETRIES):
            try:
                with httpx.Client(timeout=LLM_TIMEOUT) as client:
                    response = client.post(self._url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                    
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {401, 403}:
                    # Invalid API key, do not retry
                    raise LLMError("Invalid API key or unauthorized access.") from exc
                
                if exc.response.status_code == 429:
                    logger.warning("Rate limit hit on Groq API. Retrying...")
                    
                last_err = exc
            
            except httpx.RequestError as exc:
                logger.warning(f"Network error on Groq API attempt {attempt+1}: {exc}")
                last_err = exc

            # Exponential backoff: 2s, 4s, 8s
            time.sleep(2 ** (attempt + 1))

        logger.error("LLM Provider failed after %d retries.", LLM_MAX_RETRIES)
        raise LLMError(f"LLM generation failed: {last_err}") from last_err
