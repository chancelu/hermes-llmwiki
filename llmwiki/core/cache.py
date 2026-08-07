"""In-memory LRU cache for context retrieval — L1 RAM layer.

Avoids repeated disk reads for frequent queries.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple


class InMemoryCache:
    """Simple LRU cache with TTL expiration.

    Keys are hashed queries; values are cached context strings.
    """

    def __init__(self, maxsize: int = 100, ttl: int = 300):
        """
        Args:
            maxsize: Maximum number of entries to keep.
            ttl: Time-to-live in seconds.
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, Tuple[str, float]] = OrderedDict()

    def _make_key(self, query: str) -> str:
        """Hash a query string into a cache key."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

    def get(self, query: str) -> Optional[str]:
        """Get cached context for a query if available and not expired."""
        key = self._make_key(query)
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            # Expired
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value

    def set(self, query: str, context: str) -> None:
        """Cache context for a query."""
        key = self._make_key(query)

        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            # Evict oldest if at capacity
            while len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)

        self._cache[key] = (context, time.time())

    def invalidate(self, query: str) -> None:
        """Remove a specific query from cache."""
        key = self._make_key(query)
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        now = time.time()
        expired = sum(1 for _, ts in self._cache.values() if now - ts > self.ttl)
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "expired": expired,
            "ttl": self.ttl,
        }
