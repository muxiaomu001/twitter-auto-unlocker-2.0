"""
Proxy Forwarder - Local proxy forwarding for authenticated SOCKS5

Since Firefox/Camoufox does not support SOCKS5 proxy with authentication,
we use pproxy to create a local unauthenticated proxy that forwards
traffic to the remote authenticated proxy.
"""

import asyncio
import socket
from typing import Optional, Tuple
from dataclasses import dataclass

from ..utils.logger import get_logger
from .parser import ProxyConfig

logger = get_logger(__name__)


def _find_free_port() -> int:
    """Find a free port on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@dataclass
class ProxyForwarder:
    """
    Local proxy forwarder for authenticated SOCKS5 proxies.

    Creates a local SOCKS5 proxy without authentication that forwards
    traffic to the remote proxy with authentication.
    """

    original_proxy: ProxyConfig
    local_port: int
    _server: Optional[asyncio.Server] = None
    _task: Optional[asyncio.Task] = None

    @property
    def local_proxy(self) -> ProxyConfig:
        """Return the local proxy config (no auth needed)"""
        return ProxyConfig(
            host="127.0.0.1",
            port=self.local_port,
            username=None,
            password=None
        )

    @property
    def needs_forwarding(self) -> bool:
        """Check if the original proxy needs authentication forwarding"""
        return bool(self.original_proxy.username and self.original_proxy.password)

    async def start(self) -> "ProxyForwarder":
        """Start the local proxy forwarder using pproxy"""
        if not self.needs_forwarding:
            logger.debug("Proxy does not need forwarding (no auth)")
            return self

        try:
            import pproxy
        except ImportError:
            raise RuntimeError(
                "pproxy is required for SOCKS5 proxy authentication. "
                "Install with: pip install pproxy"
            )

        # Build pproxy connection strings
        # Local: socks5://127.0.0.1:local_port
        # Remote: socks5://host:port#username:password (pproxy uses # for auth, not @)
        local_str = f"socks5://127.0.0.1:{self.local_port}"

        # pproxy uses # to separate auth credentials, not @
        remote_str = f"socks5://{self.original_proxy.host}:{self.original_proxy.port}#{self.original_proxy.username}:{self.original_proxy.password}"

        logger.info(
            f"Starting proxy forwarder: 127.0.0.1:{self.local_port} -> "
            f"{self.original_proxy.host}:{self.original_proxy.port}"
        )

        # Create and start pproxy server
        server = pproxy.Server(local_str)
        remote = pproxy.Connection(remote_str)

        # Start the server
        self._server = await server.start_server({'rserver': [remote]})

        logger.info(f"Proxy forwarder started on port {self.local_port}")
        return self

    async def stop(self) -> None:
        """Stop the local proxy forwarder"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Proxy forwarder stopped")
            self._server = None

    def get_effective_proxy(self) -> ProxyConfig:
        """
        Get the effective proxy to use.

        Returns local proxy if forwarding is needed, otherwise original.
        """
        if self.needs_forwarding:
            return self.local_proxy
        return self.original_proxy


async def create_proxy_forwarder(proxy: ProxyConfig) -> ProxyForwarder:
    """
    Create a proxy forwarder for the given proxy config.

    If the proxy requires authentication, this will:
    1. Find a free local port
    2. Create a ProxyForwarder that listens on that port
    3. Forward traffic to the authenticated remote proxy

    Args:
        proxy: Original proxy configuration

    Returns:
        ProxyForwarder instance (call .start() to begin forwarding)
    """
    local_port = _find_free_port()
    return ProxyForwarder(
        original_proxy=proxy,
        local_port=local_port
    )
