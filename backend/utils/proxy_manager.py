"""
Proxy manager for rotating proxies during scraping.
Supports HTTP and SOCKS5 proxies with round-robin rotation.
"""

import random
from typing import Optional
from config import PROXY_LIST, PROXY_ENABLED


class ProxyManager:
    """Manages proxy rotation for scraping sessions."""

    def __init__(self):
        self._proxies = PROXY_LIST.copy()
        self._index = 0

    @property
    def enabled(self) -> bool:
        return PROXY_ENABLED and len(self._proxies) > 0

    def get_next_proxy(self) -> Optional[dict]:
        """
        Get the next proxy in rotation.
        Returns Playwright-compatible proxy dict or None.
        """
        if not self.enabled:
            return None

        proxy_url = self._proxies[self._index % len(self._proxies)]
        self._index += 1

        return self._parse_proxy_url(proxy_url)

    def get_random_proxy(self) -> Optional[dict]:
        """Get a random proxy from the pool."""
        if not self.enabled:
            return None

        proxy_url = random.choice(self._proxies)
        return self._parse_proxy_url(proxy_url)

    def _parse_proxy_url(self, proxy_url: str) -> dict:
        """
        Parse a proxy URL into Playwright's expected format.
        Input:  "http://user:pass@host:port" or "socks5://host:port"
        Output: {"server": "http://host:port", "username": "user", "password": "pass"}
        """
        proxy_dict = {"server": proxy_url}

        # Extract credentials if present
        if "@" in proxy_url:
            # Split protocol and rest
            protocol, rest = proxy_url.split("://", 1)
            creds, host_port = rest.rsplit("@", 1)

            if ":" in creds:
                username, password = creds.split(":", 1)
                proxy_dict = {
                    "server": f"{protocol}://{host_port}",
                    "username": username,
                    "password": password,
                }

        return proxy_dict

    def add_proxy(self, proxy_url: str):
        """Add a proxy to the pool at runtime."""
        if proxy_url not in self._proxies:
            self._proxies.append(proxy_url)

    def remove_proxy(self, proxy_url: str):
        """Remove a failed proxy from the pool."""
        if proxy_url in self._proxies:
            self._proxies.remove(proxy_url)

    @property
    def pool_size(self) -> int:
        return len(self._proxies)


# Singleton instance
proxy_manager = ProxyManager()
