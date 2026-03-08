"""HTTP Tool with connection pooling for improved performance.

This module provides HTTP tools with aiohttp connection pooling
to reduce TCP handshake overhead and improve response times.
"""

import asyncio
from typing import Any

import aiohttp

from .base import Tool, ToolResult


class HTTPClientManager:
    """Singleton manager for aiohttp ClientSession with connection pooling.

    This manager maintains a shared ClientSession with connection pooling
to reuse TCP connections across multiple HTTP requests, reducing latency.
    """

    _instance: "HTTPClientManager | None" = None
    _lock: asyncio.Lock | None = None

    def __new__(cls) -> "HTTPClientManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._session: aiohttp.ClientSession | None = None
            cls._instance._connector: aiohttp.TCPConnector | None = None
            cls._instance._ref_count = 0
        return cls._instance

    @property
    def _lock_instance(self) -> asyncio.Lock:
        """Lazy initialization of lock."""
        if self._lock is None:
            HTTPClientManager._lock = asyncio.Lock()
        return HTTPClientManager._lock

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create shared ClientSession with connection pool.

        Returns:
            aiohttp.ClientSession with connection pooling enabled.
        """
        async with self._lock_instance:
            if self._session is None or self._session.closed:
                # Configure TCP connector with connection pooling
                self._connector = aiohttp.TCPConnector(
                    limit=100,              # Total connection pool size
                    limit_per_host=20,      # Connections per host
                    ttl_dns_cache=300,      # DNS cache TTL (5 minutes)
                    use_dns_cache=True,     # Enable DNS caching
                    keepalive_timeout=60,   # Keep-alive timeout
                    enable_cleanup_closed=True,  # Clean up closed connections
                )

                # Configure session with timeout and connector
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self._session = aiohttp.ClientSession(
                    connector=self._connector,
                    timeout=timeout,
                    headers={
                        "User-Agent": "Heris-Agent/0.1.0",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                    },
                )

            self._ref_count += 1
            return self._session

    async def release(self) -> None:
        """Release reference to shared session.

        When reference count reaches 0, the session is kept alive
        for a grace period to allow reuse.
        """
        async with self._lock_instance:
            self._ref_count = max(0, self._ref_count - 1)

    async def close(self) -> None:
        """Close the shared session and cleanup resources."""
        async with self._lock_instance:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
            if self._connector:
                await self._connector.close()
                self._connector = None
            self._ref_count = 0


class WebFetchTool(Tool):
    """Fetch content from a web URL using connection pooling.

    Uses shared aiohttp ClientSession for connection reuse,
    significantly reducing latency for multiple requests.
    """

    def __init__(self):
        """Initialize WebFetchTool."""
        super().__init__()  # Initialize schema cache
        self._client_manager = HTTPClientManager()

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch content from a web URL. Supports HTML pages and returns "
            "extracted text content. Uses connection pooling for efficient "
            "multiple requests. Handles timeouts and errors gracefully."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, timeout: int = 30) -> ToolResult:
        """Fetch content from URL using connection pooled HTTP client.

        Args:
            url: The URL to fetch
            timeout: Request timeout in seconds

        Returns:
            ToolResult with fetched content or error
        """
        session = None
        try:
            # Get shared session with connection pooling
            session = await self._client_manager.get_session()

            # Configure request-specific timeout
            request_timeout = aiohttp.ClientTimeout(total=timeout)

            async with session.get(url, timeout=request_timeout) as response:
                response.raise_for_status()

                # Get content type
                content_type = response.headers.get("Content-Type", "").lower()

                # Read text content
                text = await response.text()

                # Simple HTML to text extraction (basic)
                if "text/html" in content_type:
                    text = self._extract_text_from_html(text)

                # Truncate if too long
                if len(text) > 50000:
                    text = text[:50000] + "\n... [Content truncated]"

                return ToolResult(
                    success=True,
                    content=text,
                )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                content="",
                error=f"Request timed out after {timeout}s for URL: {url}",
            )
        except aiohttp.ClientError as e:
            return ToolResult(
                success=False,
                content="",
                error=f"HTTP error fetching {url}: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to fetch {url}: {str(e)}",
            )
        finally:
            # Release reference to shared session
            if session:
                await self._client_manager.release()

    def _extract_text_from_html(self, html: str) -> str:
        """Basic HTML to text extraction.

        Args:
            html: HTML content

        Returns:
            Extracted text
        """
        import re

        # Remove script and style tags and their content
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()


# Global cleanup function for graceful shutdown
async def cleanup_http_clients() -> None:
    """Cleanup all HTTP client resources on shutdown."""
    manager = HTTPClientManager()
    await manager.close()
