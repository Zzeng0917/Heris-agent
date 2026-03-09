"""Web/HTTP tools.

This module provides tools for web operations:
- WebFetchTool: Fetch content from web URLs
- WebSearchTool: Search the web for real-time information
- HTTPClientManager: Connection pooling manager for HTTP requests
- cleanup_http_clients: Cleanup function for graceful shutdown
"""

from .fetch import WebFetchTool, cleanup_http_clients
from .search import WebSearchTool, WebSearchResult
from .client import HTTPClientManager

__all__ = [
    "WebFetchTool",
    "WebSearchTool",
    "WebSearchResult",
    "HTTPClientManager",
    "cleanup_http_clients",
]
