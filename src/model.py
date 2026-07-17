"""Model abstraction layer for the UofT Course Planning Agent.

This module defines a base interface for language models and provides a
deterministic mock implementation for testing as well as a Tencent
TokenHub backend.  The interface is designed so that future backends
(DeepSeek, Claude, OpenAI-compatible APIs) can be swapped in without
changing the agent layer.
"""

import os


class BaseModelInterface:
    """Abstract interface for a language model backend.

    Subclasses must implement :meth:`generate_response`.
    """

    def generate_response(self, messages: list[dict]) -> str:
        """Generate a response from a list of chat messages.

        Args:
            messages: A list of dicts with ``role`` and ``content`` keys,
                following the standard chat-completion message format.

        Returns:
            A string response from the model.

        Raises:
            NotImplementedError: If the subclass does not override this
                method.
        """
        raise NotImplementedError(
            "Subclasses must implement generate_response()."
        )


class MockModel(BaseModelInterface):
    """A deterministic mock model that returns a placeholder response.

    This model does **not** call any external API.  It is suitable for
    testing the agent pipeline without network access or API keys.
    """

    def generate_response(self, messages: list[dict]) -> str:
        """Return a deterministic placeholder string.

        Args:
            messages: Chat messages (ignored by this implementation).

        Returns:
            The string ``"Mock model response"``.
        """
        return "Mock model response"


class TencentTokenHubModel(BaseModelInterface):
    """A model backend that calls the Tencent TokenHub API.

    TokenHub provides an OpenAI-compatible Chat Completions endpoint.
    Credentials are read from environment variables:

    * ``TOKENHUB_API_KEY`` — the API key (required).
    * ``TOKENHUB_BASE_URL`` — the base URL of the TokenHub endpoint
      (required).
    * ``TOKENHUB_MODEL`` — the model name to use (required).

    Example::

        model = TencentTokenHubModel()
        response = model.generate_response(
            [{"role": "user", "content": "Hello"}]
        )
    """

    def __init__(self):
        """Initialise the TokenHub model backend.

        Raises:
            ValueError: If any required environment variable is missing.
        """
        self.api_key = os.environ.get("TOKENHUB_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError(
                "TOKENHUB_API_KEY environment variable is not set."
            )

        self.base_url = os.environ.get("TOKENHUB_BASE_URL", "").strip()
        if not self.base_url:
            raise ValueError(
                "TOKENHUB_BASE_URL environment variable is not set."
            )

        self.model_name = os.environ.get("TOKENHUB_MODEL", "").strip()
        if not self.model_name:
            raise ValueError(
                "TOKENHUB_MODEL environment variable is not set."
            )

    def generate_response(self, messages: list[dict]) -> str:
        """Send messages to TokenHub and return the assistant response.

        Args:
            messages: Chat messages in OpenAI format.

        Returns:
            The content of the assistant message.

        Raises:
            RuntimeError: If the API call fails.
        """
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=False,
            )
            return completion.choices[0].message.content
        except Exception as exc:
            raise RuntimeError(
                f"TokenHub API call failed: {exc}"
            ) from exc
