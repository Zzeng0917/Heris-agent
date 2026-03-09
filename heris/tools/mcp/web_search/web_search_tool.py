"""Web Search Tool - Search the web for real-time information.

This tool performs web searches to fetch the latest information and news,
helping overcome the LLM's knowledge cutoff limitation.
"""

import asyncio
import re
import urllib.parse
from typing import Any

from ...base import Tool, ToolResult


class WebSearchResult(ToolResult):
    """Web search result with structured data."""

    def __init__(
        self,
        success: bool,
        content: str = "",
        error: str | None = None,
        results: list[dict] | None = None,
        total_results: int = 0,
    ):
        super().__init__(success=success, content=content, error=error)
        self.results = results or []
        self.total_results = total_results


class WebSearchTool(Tool):
    """Tool for searching the web to get real-time information.

    This tool performs web searches using search engines to fetch
    the latest news and information that may not be in the LLM's
    training data.

    Example usage:
    - Search for latest news about a company
    - Get real-time stock prices or market data
    - Find recent developments in a field
    - Verify facts about current events
    """

    def __init__(self):
        """Initialize WebSearchTool."""
        super().__init__()

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for real-time information and news. "
            "Use this when you need up-to-date information beyond your knowledge cutoff, "
            "such as recent events, current news, stock prices, or real-time data. "
            "Returns search results with titles, URLs, snippets, and dates."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string. Be specific and include relevant keywords, dates, or entities for better results.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return (default: 10, max: 20).",
                    "default": 10,
                },
                "time_range": {
                    "type": "string",
                    "description": "Time filter for results: 'day', 'week', 'month', 'year', or omit for all time.",
                    "enum": ["day", "week", "month", "year"],
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        max_results: int = 10,
        time_range: str | None = None,
    ) -> WebSearchResult:
        """Execute web search.

        Args:
            query: The search query string
            max_results: Maximum number of results (default: 10)
            time_range: Time filter (day/week/month/year)

        Returns:
            WebSearchResult with search results
        """
        try:
            # Validate and limit max_results
            max_results = min(max(1, max_results), 20)

            # Try DuckDuckGo search first (no API key needed)
            results = await self._search_duckduckgo(query, max_results, time_range)

            if not results:
                return WebSearchResult(
                    success=True,
                    content=f"No results found for query: '{query}'",
                    results=[],
                    total_results=0,
                )

            # Format results
            formatted = self._format_results(query, results)

            return WebSearchResult(
                success=True,
                content=formatted,
                results=results,
                total_results=len(results),
            )

        except Exception as e:
            return WebSearchResult(
                success=False,
                content="",
                error=f"Web search failed: {str(e)}",
            )

    async def _search_duckduckgo(
        self,
        query: str,
        max_results: int,
        time_range: str | None = None,
    ) -> list[dict]:
        """Search using DuckDuckGo HTML interface.

        Args:
            query: Search query
            max_results: Max results to return
            time_range: Time filter

        Returns:
            List of search result dicts
        """
        import aiohttp

        # Build search URL
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        # Add time range parameter if specified
        if time_range:
            time_param = {
                "day": "d",
                "week": "w",
                "month": "m",
                "year": "y",
            }.get(time_range)
            if time_param:
                url += f"&df={time_param}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as response:
                response.raise_for_status()
                html = await response.text()

        return self._parse_duckduckgo_results(html, max_results)

    def _parse_duckduckgo_results(self, html: str, max_results: int) -> list[dict]:
        """Parse DuckDuckGo HTML results.

        Args:
            html: HTML response
            max_results: Max results to extract

        Returns:
            List of result dicts
        """
        results = []

        # Simple regex-based parsing for DuckDuckGo HTML
        # Look for result blocks
        result_blocks = re.findall(
            r'<div class="result[^"]*"[^>]*>.*?<\/div>\s*<\/div>\s*<\/div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for block in result_blocks[:max_results]:
            result = {}

            # Extract title and URL
            title_match = re.search(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if title_match:
                href = title_match.group(1)
                # DuckDuckGo uses redirect URLs
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = "https://duckduckgo.com" + href

                # Extract actual URL from redirect if present
                redirect_match = re.search(r"uddg=([^&]+)", href)
                if redirect_match:
                    href = urllib.parse.unquote(redirect_match.group(1))

                result["url"] = href
                result["title"] = re.sub(r"<[^>]+>", "", title_match.group(2)).strip()

            # Extract snippet
            snippet_match = re.search(
                r'<a[^>]*class="result__snippet"[^>]*>(.*?)<\/a>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if snippet_match:
                snippet = snippet_match.group(1)
                snippet = re.sub(r"<[^>]+>", " ", snippet)
                snippet = re.sub(r"\s+", " ", snippet).strip()
                result["snippet"] = snippet

            # Try to extract date
            date_match = re.search(
                r'<span class="result__timestamp"[^>]*>(.*?)<\/span>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if date_match:
                result["date"] = re.sub(r"<[^>]+>", "", date_match.group(1)).strip()

            if result.get("title") and result.get("url"):
                results.append(result)

        return results

    def _format_results(self, query: str, results: list[dict]) -> str:
        """Format search results for display.

        Args:
            query: Original query
            results: List of result dicts

        Returns:
            Formatted string
        """
        lines = [f'Search Results for "{query}":\n']

        for i, result in enumerate(results, 1):
            lines.append(f"{i}. {result.get('title', 'No Title')}")
            lines.append(f"   URL: {result.get('url', 'N/A')}")
            if result.get("snippet"):
                lines.append(f"   Snippet: {result['snippet'][:200]}...")
            if result.get("date"):
                lines.append(f"   Date: {result['date']}")
            lines.append("")

        lines.append(f"Total results: {len(results)}")
        return "\n".join(lines)
