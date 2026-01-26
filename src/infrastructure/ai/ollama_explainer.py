"""
Ollama (local) explainer adapter.

Implements AIExplainer port using Ollama HTTP API.

Layer: Infrastructure
"""

import os
from urllib.error import URLError

from src.domain.ports.ai_explainer import (
    ExplainerError,
    ExplainerTimeoutError,
)
from src.infrastructure.ai.base_explainer import (
    LLM_MAX_TOKENS,
    LLM_TIMEOUT_SECONDS,
    BaseExplainer,
)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:1.5b"


class OllamaExplainer(BaseExplainer):
    """Local Ollama server adapter for explanations.

    Uses the Ollama HTTP API directly to avoid additional dependencies.
    """

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
    ):
        """Initialize Ollama explainer.

        Args:
            host: Ollama server URL. Defaults to OLLAMA_HOST env or localhost:11434.
            model: Model name. Defaults to OLLAMA_MODEL env or qwen2.5:1.5b.
        """
        self._host = host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        self._model = model or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)

    @property
    def provider_name(self) -> str:
        return f"ollama:{self._model}"

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int]:
        """Call Ollama API via HTTP."""
        import json
        import urllib.request

        url = f"{self._host.rstrip('/')}/api/chat"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": LLM_MAX_TOKENS,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))

            text = result.get("message", {}).get("content", "")

            # Ollama returns token counts in different fields
            total_tokens = result.get("prompt_eval_count", 0) + result.get("eval_count", 0)

            return text, total_tokens

        except TimeoutError:
            raise ExplainerTimeoutError(f"Ollama request timed out after {LLM_TIMEOUT_SECONDS}s")
        except URLError as e:
            if "timed out" in str(e).lower():
                raise ExplainerTimeoutError(f"Ollama request timed out: {e}")
            raise ExplainerError(
                f"Failed to connect to Ollama at {self._host}: {e}. "
                "Is Ollama running? Start with: ollama serve"
            )
        except json.JSONDecodeError as e:
            raise ExplainerError(f"Invalid response from Ollama: {e}")
        except Exception as e:
            raise ExplainerError(f"Ollama error: {e}")
