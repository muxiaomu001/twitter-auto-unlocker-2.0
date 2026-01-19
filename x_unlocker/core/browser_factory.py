"""
Browser Factory - 浏览器提供者工厂 (2.0 版本)

根据配置创建 BitBrowser 浏览器提供者实例。

版本: 2.0 - 仅支持 BitBrowser
"""

from contextlib import asynccontextmanager
from typing import Optional

from .bitbrowser_provider import BitBrowserProvider
from .bitbrowser_client import BitBrowserConfig
from ..proxy.parser import ProxyConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def create_browser_provider(
    # BitBrowser 参数
    bitbrowser_api: str = "http://127.0.0.1:54345",
    proxy: Optional[ProxyConfig] = None,
    browser_name: Optional[str] = None,
    page_timeout: int = 60000,
):
    """
    创建 BitBrowser 浏览器提供者（上下文管理器）

    Args:
        bitbrowser_api: BitBrowser API 地址
        proxy: 代理配置
        browser_name: 浏览器名称（自动生成如不指定）
        page_timeout: 页面超时（毫秒）

    Yields:
        BitBrowserProvider 实例

    Example:
        async with create_browser_provider() as browser:
            await browser.navigate("https://x.com")

        # 指定代理
        async with create_browser_provider(proxy=proxy_config) as browser:
            await browser.navigate("https://x.com")
    """
    config = BitBrowserConfig(api_url=bitbrowser_api)
    provider = BitBrowserProvider(
        config=config,
        proxy=proxy,
        browser_name=browser_name,
        page_timeout=page_timeout
    )
    logger.info(f"Using BitBrowser provider (API: {bitbrowser_api})")

    try:
        await provider.start()
        yield provider
    finally:
        await provider.close()


async def create_browser_for_account(
    account_id: str,
    bitbrowser_api: str = "http://127.0.0.1:54345",
    proxy: Optional[ProxyConfig] = None,
    page_timeout: int = 60000,
) -> BitBrowserProvider:
    """
    为指定账号创建浏览器（非上下文管理器，需手动关闭）

    Args:
        account_id: 账号标识（用于生成浏览器名称）
        bitbrowser_api: BitBrowser API 地址
        proxy: 代理配置
        page_timeout: 页面超时（毫秒）

    Returns:
        BitBrowserProvider 实例

    Note:
        使用完毕后需要调用 await provider.close() 关闭浏览器
    """
    config = BitBrowserConfig(api_url=bitbrowser_api)
    provider = BitBrowserProvider(
        config=config,
        proxy=proxy,
        browser_name=f"unlock_{account_id}",
        page_timeout=page_timeout
    )

    logger.info(f"Creating browser for account: {account_id}")
    await provider.start()
    return provider


__all__ = [
    "create_browser_provider",
    "create_browser_for_account",
    "BitBrowserProvider",
    "BitBrowserConfig",
]
