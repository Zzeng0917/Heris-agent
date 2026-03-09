"""HTTP client with connection pooling for improved performance."""

import asyncio

import aiohttp


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
