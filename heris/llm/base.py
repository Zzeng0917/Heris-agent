"""Base class for LLM clients."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from ..retry import RetryConfig
from ..schema import LLMResponse, Message, StreamChunk


class LLMClientBase(ABC):
    """Abstract base class for LLM clients.

    This class defines the interface that all LLM clients must implement,
    regardless of the underlying API protocol (Anthropic, OpenAI, etc.).
    """

    # Default timeout for API requests (in seconds)
    DEFAULT_TIMEOUT = 180  # 3 minutes

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        retry_config: RetryConfig | None = None,
        timeout: float | None = None,
    ):
        """Initialize the LLM client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API
            model: Model name to use
            retry_config: Optional retry configuration
            timeout: Request timeout in seconds (default: 180s)
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.retry_config = retry_config or RetryConfig()
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Callback for tracking retry count
        self.retry_callback = None

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMResponse:
        """Generate response from LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts

        Returns:
            LLMResponse containing the generated content, thinking, and tool calls
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Generate streaming response from LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts

        Yields:
            StreamChunk containing a piece of the generated content
        """
        pass

    @abstractmethod
    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request payload for the API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing the request payload
        """
        pass

    @abstractmethod
    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal message format to API-specific format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        pass
