"""
登录流程辅助模块

功能:
- 登录表单交互辅助方法
- 页面状态检测
- 错误页面处理
- 浏览器预热
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from ..utils.logger import get_logger
from ..utils.helpers import human_delay, HUMAN_DELAY_MIN, HUMAN_DELAY_MAX

if TYPE_CHECKING:
    from ..core.browser import BrowserManager


class LoginFlowHelper:
    """登录流程辅助器"""

    # 选择器
    SELECTORS = {
        # 登录页面就绪检测
        "login_page_ready": 'input[autocomplete="username"], h1:has-text("Sign in"), h1:has-text("登录")',

        # 错误页面检测
        "error_page": 'text="Something went wrong", text="出错了"',
        "retry_button": 'text="Try again", text="Retry", text="重试"',
    }

    def __init__(
        self,
        browser: "BrowserManager",
        account_id: Optional[str] = None
    ):
        """
        初始化辅助器

        Args:
            browser: 浏览器管理器
            account_id: 账号标识（用于日志）
        """
        self.browser = browser
        self._logger = get_logger(__name__, account_id=account_id)

    async def wait_and_type(
        self,
        selector: str,
        text: str,
        timeout: int = 10000
    ) -> bool:
        """
        等待元素并输入文本

        Args:
            selector: CSS 选择器
            text: 要输入的文本
            timeout: 超时时间（毫秒）

        Returns:
            是否成功
        """
        try:
            element = await self.browser.page.wait_for_selector(
                selector,
                timeout=timeout,
                state="visible"
            )
            if element:
                await element.click()
                await asyncio.sleep(0.2)
                await element.fill("")  # 清空
                await element.type(text, delay=50)
                return True
        except Exception as e:
            self._logger.debug(f"等待元素 {selector} 超时: {e}")
        return False

    async def wait_and_click(
        self,
        selector: str,
        timeout: int = 10000
    ) -> bool:
        """
        等待元素并点击

        Args:
            selector: CSS 选择器
            timeout: 超时时间（毫秒）

        Returns:
            是否成功
        """
        try:
            element = await self.browser.page.wait_for_selector(
                selector,
                timeout=timeout,
                state="visible"
            )
            if element:
                await element.click()
                await asyncio.sleep(0.5)
                return True
        except Exception as e:
            self._logger.debug(f"等待元素 {selector} 超时: {e}")
        return False

    async def check_for_error_page(self) -> bool:
        """
        检查是否出现 'Something went wrong' 错误页面

        Returns:
            是否出现错误页面
        """
        page = self.browser.page
        try:
            error_el = await page.query_selector(self.SELECTORS["error_page"])
            if error_el:
                return True
        except:
            pass
        return False

    async def handle_error_page(self) -> bool:
        """
        处理错误页面，尝试刷新

        Returns:
            是否成功处理
        """
        self._logger.warning("检测到错误页面，尝试刷新...")
        page = self.browser.page

        # 尝试点击重试按钮
        try:
            retry_btn = await page.query_selector(self.SELECTORS["retry_button"])
            if retry_btn:
                await retry_btn.click()
                await human_delay(2, 4)
                return True
        except:
            pass

        # 如果没有重试按钮，直接刷新页面
        try:
            await page.reload()
            await human_delay(3, 5)
            return True
        except:
            pass

        return False

    async def wait_for_page_ready(self, timeout: int = 15000) -> bool:
        """
        等待页面完全就绪

        Args:
            timeout: 超时时间（毫秒）

        Returns:
            页面是否就绪
        """
        page = self.browser.page

        try:
            # 等待网络空闲
            await page.wait_for_load_state("networkidle", timeout=timeout)

            # 额外等待 - 确保 JS 渲染完成
            await human_delay(1, 2)

            # 检查页面是否有实际内容（不只是 loading 状态）
            body_content = await page.evaluate("document.body.innerText.length")
            if body_content < 50:  # 页面内容太少，可能还在加载
                self._logger.debug("页面内容较少，等待更多加载...")
                await human_delay(2, 3)

            return True
        except Exception as e:
            self._logger.warning(f"等待页面就绪超时: {e}")
            return False

    async def warm_up_browser(self, cloudflare_handler=None) -> None:
        """
        浏览器预热 - 先访问一些正常页面建立信任

        这有助于避免直接访问登录页被检测为自动化

        Args:
            cloudflare_handler: Cloudflare 处理器（可选）
        """
        self._logger.info("浏览器预热中...")
        page = self.browser.page

        try:
            # 先访问 X 首页（无需登录的公开页面）
            await page.goto("https://x.com", wait_until="networkidle", timeout=30000)
            await human_delay(2, 4)

            # 检测 Cloudflare 阻塞
            if cloudflare_handler:
                if await cloudflare_handler.check_cloudflare_block():
                    self._logger.warning("预热阶段检测到 Cloudflare 阻塞")
                    await cloudflare_handler.handle_cloudflare_block()
                    await human_delay(2, 3)

            # 模拟一些人类行为 - 滚动页面
            await page.mouse.wheel(0, 300)
            await human_delay(0.5, 1)
            await page.mouse.wheel(0, -150)
            await human_delay(1, 2)

            self._logger.info("浏览器预热完成")
        except Exception as e:
            self._logger.warning(f"预热过程出现问题（可忽略）: {e}")
