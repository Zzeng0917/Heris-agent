"""Web fetch tool."""

import asyncio
from typing import Any

from ..base import Tool, ToolResult
from .client import HTTPClientManager


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
            import aiohttp
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
        except Exception as e:
            import aiohttp
            if isinstance(e, aiohttp.ClientError):
                return ToolResult(
                    success=False,
                    content="",
                    error=f"HTTP error fetching {url}: {str(e)}",
                )
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
        import html as html_module
        import re

        # Remove script and style tags and their content
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Decode HTML entities
        text = html_module.unescape(text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()


# Global cleanup function for graceful shutdown
async def cleanup_http_clients() -> None:
    """Cleanup all HTTP client resources on shutdown."""
    manager = HTTPClientManager()
    await manager.close()
