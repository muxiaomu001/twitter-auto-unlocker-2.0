"""
Proxy Module - Proxy parsing and forwarding

Exports:
- ProxyConfig: Proxy configuration dataclass
- parse_proxy: Parse proxy string
- ProxyForwarder: Local proxy forwarding for authenticated SOCKS5
- create_proxy_forwarder: Create proxy forwarder instance
"""

from .parser import ProxyConfig, parse_proxy
from .forwarder import ProxyForwarder, create_proxy_forwarder

__all__ = [
    "ProxyConfig",
    "parse_proxy",
    "ProxyForwarder",
    "create_proxy_forwarder",
]
