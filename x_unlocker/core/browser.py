"""
Browser Module - BitBrowser browser initialization and management (2.0)

Features:
- Launch browser using BitBrowser API
- Automatic fingerprint rotation (each instance has unique fingerprint)
- SOCKS5 proxy configuration with authentication support

Note:
    This module provides backward compatibility with existing code.
    New code should use browser_factory.py or directly use providers.
"""

from contextlib import asynccontextmanager
from typing import Optional, Tuple

from .bitbrowser_provider import BitBrowserProvider
from .bitbrowser_client import BitBrowserConfig
from .errors import BrowserNotStartedError
from ..proxy.parser import ProxyConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Backward compatibility alias
BrowserManager = BitBrowserProvider


@asynccontextmanager
async def create_browser(
    proxy: Optional[ProxyConfig] = None,
    headless: bool = False,
    page_timeout: int = 60000
):
    """
    Create browser (context manager)

    This function provides backward compatibility with existing code.
    For new code, consider using browser_factory.create_browser_provider().

    Args:
        proxy: Proxy configuration (optional, None for direct connection)
        headless: Whether to run in headless mode (ignored for BitBrowser)
        page_timeout: Page timeout in milliseconds

    Yields:
        BrowserManager (BitBrowserProvider) instance

    Example:
        async with create_browser() as browser:
            await browser.navigate("https://x.com")
    """
    manager = BitBrowserProvider(
        proxy=proxy,
        page_timeout=page_timeout
    )
    try:
        await manager.start()
        yield manager
    finally:
        await manager.close()


async def create_browser_simple(
    proxy: Optional[ProxyConfig] = None,
    headless: bool = False,
    page_timeout: int = 60000
) -> Tuple:
    """
    Simple browser creation (returns browser and page)

    Note: Caller must close the browser manually

    Args:
        proxy: Proxy configuration (optional, None for direct connection)
        headless: Whether to run in headless mode (ignored for BitBrowser)
        page_timeout: Page timeout in milliseconds

    Returns:
        (BrowserManager, page) tuple
    """
    manager = BitBrowserProvider(
        proxy=proxy,
        page_timeout=page_timeout
    )
    await manager.start()
    return manager, manager.page
