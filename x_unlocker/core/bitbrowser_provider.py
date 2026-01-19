"""
BitBrowser Provider - 比特浏览器提供者实现

通过 BitBrowser API 动态创建浏览器窗口，使用 Playwright CDP 连接。

工作流程:
1. 调用 API 创建新浏览器配置
2. 打开浏览器窗口获取 WebSocket 端口
3. Playwright 通过 CDP 连接到浏览器
4. 执行自动化操作
5. 关闭窗口并删除配置
"""

import asyncio
from typing import Optional, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .browser_provider import BrowserProvider
from .bitbrowser_client import BitBrowserClient, BitBrowserConfig, BitBrowserError
from .errors import BrowserNotStartedError, BrowserStartError
from ..proxy.parser import ProxyConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BitBrowserProvider(BrowserProvider):
    """
    比特浏览器提供者

    动态创建 BitBrowser 窗口并通过 Playwright CDP 连接。
    任务完成后自动清理（关闭窗口、删除配置）。
    """

    def __init__(
        self,
        config: Optional[BitBrowserConfig] = None,
        proxy: Optional[ProxyConfig] = None,
        browser_name: Optional[str] = None,
        page_timeout: int = 60000,
        reuse_browser_id: Optional[str] = None,
    ):
        """
        初始化 BitBrowser Provider

        Args:
            config: BitBrowser 配置
            proxy: 代理配置（可选）
            browser_name: 浏览器名称（自动生成如不指定）
            page_timeout: 页面超时（毫秒）
            reuse_browser_id: 复用已有的浏览器 ID（避免创建新配置）
        """
        self.config = config or BitBrowserConfig()
        self.proxy = proxy
        self.browser_name = browser_name
        self.page_timeout = page_timeout
        self._reuse_browser_id = reuse_browser_id
        self._should_delete = reuse_browser_id is None  # 只有新创建的才删除

        self._client = BitBrowserClient(self.config)
        self._browser_id: Optional[str] = None
        self._ws_endpoint: Optional[str] = None
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> "BitBrowserProvider":
        """
        启动 BitBrowser

        1. 创建浏览器配置（或复用已有配置）
        2. 打开浏览器窗口
        3. 连接到浏览器
        """
        logger.info("Starting BitBrowser provider...")

        try:
            # 1. 检查 BitBrowser 连接
            if not await self._client.check_connection():
                raise BrowserStartError(
                    "无法连接到 BitBrowser，请确保 BitBrowser 客户端已启动"
                )

            # 2. 获取或创建浏览器配置
            if self._reuse_browser_id:
                # 复用已有配置
                self._browser_id = self._reuse_browser_id
                logger.info(f"复用已有浏览器配置: {self._browser_id}")
            else:
                # 创建新配置
                self._browser_id = await self._client.create_browser(
                    name=self.browser_name,
                    proxy=self.proxy
                )

            # 3. 打开浏览器窗口
            self._ws_endpoint = await self._client.open_browser(self._browser_id)

            # 4. 使用 Playwright CDP 连接
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._ws_endpoint
            )

            # 5. 获取现有的 context 和 page
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                pages = self._context.pages
                if pages:
                    self._page = pages[0]
                else:
                    self._page = await self._context.new_page()
            else:
                # 如果没有现有 context，创建新的
                self._context = await self._browser.new_context()
                self._page = await self._context.new_page()

            # 6. 设置超时
            self._page.set_default_timeout(self.page_timeout)

            logger.info("BitBrowser provider started successfully")
            return self

        except BitBrowserError as e:
            await self._cleanup()
            raise BrowserStartError(f"BitBrowser 启动失败: {e}")
        except Exception as e:
            await self._cleanup()
            raise BrowserStartError(f"连接 BitBrowser 失败: {e}")

    async def _cleanup(self) -> None:
        """清理资源"""
        # 断开 Playwright 连接
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug(f"断开浏览器连接时出错: {e}")
            self._browser = None
            self._context = None
            self._page = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug(f"停止 Playwright 时出错: {e}")
            self._playwright = None

        # 关闭并删除浏览器配置（仅对新创建的配置执行删除）
        if self._browser_id:
            await self._client.close_browser(self._browser_id)
            if self._should_delete:
                await self._client.delete_browser(self._browser_id)
            self._browser_id = None

        # 关闭 HTTP 客户端
        await self._client.close()

    async def close(self) -> None:
        """关闭连接并清理资源"""
        logger.info("Closing BitBrowser provider...")
        await self._cleanup()
        logger.info("BitBrowser provider closed")

    @property
    def page(self) -> Page:
        """获取当前页面"""
        if not self._page:
            raise BrowserNotStartedError("BitBrowser 未连接")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """获取浏览器上下文"""
        if not self._context:
            raise BrowserNotStartedError("BitBrowser 未连接")
        return self._context

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        """导航到 URL"""
        logger.debug(f"Navigating to: {url}")
        await self.page.goto(url, wait_until=wait_until)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

    async def screenshot(
        self,
        path: str,
        full_page: bool = False,
        wait_before: float = 0.5
    ) -> None:
        """保存截图"""
        if wait_before > 0:
            await asyncio.sleep(wait_before)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        await self.page.screenshot(path=path, full_page=full_page)
        logger.debug(f"Screenshot saved: {path}")

    async def wait_for_selector(
        self,
        selector: str,
        timeout: Optional[int] = None,
        state: str = "visible"
    ) -> Any:
        """等待元素"""
        return await self.page.wait_for_selector(
            selector,
            timeout=timeout,
            state=state
        )

    async def type_text(
        self,
        selector: str,
        text: str,
        delay: int = 50
    ) -> None:
        """输入文本"""
        element = await self.wait_for_selector(selector)
        await element.click()
        await asyncio.sleep(0.1)
        await element.type(text, delay=delay)

    async def click(self, selector: str, wait_after: float = 0.5) -> None:
        """点击元素"""
        element = await self.wait_for_selector(selector)
        await element.click()
        if wait_after > 0:
            await asyncio.sleep(wait_after)

    async def get_user_agent(self) -> Optional[str]:
        """获取 User-Agent"""
        try:
            return await self.page.evaluate("navigator.userAgent")
        except Exception as e:
            logger.debug(f"获取 User-Agent 失败: {e}")
            return None
