"""
Browser Module - Camoufox browser initialization and management

Features:
- Launch Firefox browser using Camoufox
- Automatic fingerprint rotation (each instance has unique fingerprint)
- SOCKS5 proxy configuration with authentication support

Note:
    This module provides backward compatibility with existing code.
    New code should use browser_factory.py or directly use providers.
"""

from contextlib import asynccontextmanager
from typing import Optional, Tuple

from .camoufox_provider import CamoufoxProvider
from .errors import BrowserNotStartedError
from ..proxy.parser import ProxyConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Backward compatibility alias
BrowserManager = CamoufoxProvider


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
        headless: Whether to run in headless mode
        page_timeout: Page timeout in milliseconds

    Yields:
        BrowserManager (CamoufoxProvider) instance

    Example:
        async with create_browser() as browser:
            await browser.navigate("https://x.com")
    """
    manager = CamoufoxProvider(
        proxy=proxy,
        headless=headless,
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
        headless: Whether to run in headless mode
        page_timeout: Page timeout in milliseconds

    Returns:
        (BrowserManager, page) tuple
    """
    manager = CamoufoxProvider(
        proxy=proxy,
        headless=headless,
        page_timeout=page_timeout
    )
    await manager.start()
    return manager, manager.page
