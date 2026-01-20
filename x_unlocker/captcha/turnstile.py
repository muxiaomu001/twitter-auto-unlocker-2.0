"""
Cloudflare Turnstile 处理模块 (2.0 版本)

2.0 版本中，Turnstile 验证码由 YesCaptcha 人机助手插件自动处理。
本模块仅负责检测和等待验证完成。
"""

import asyncio
from typing import Optional, Tuple

from .base import BaseCaptchaHandler
from ..core.browser import BrowserManager
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TurnstileHandler(BaseCaptchaHandler):
    """Cloudflare Turnstile 处理器 (2.0 - 插件模式)"""

    # Turnstile 相关选择器
    SELECTORS = {
        "iframe": 'iframe[src*="challenges.cloudflare.com"]',
        "container": '.cf-turnstile, [data-sitekey]',
        "response_input": 'input[name="cf-turnstile-response"]',
        "success_indicator": '.cf-turnstile[data-response], input[name="cf-turnstile-response"][value]:not([value=""])',
    }

    # 插件等待配置
    MAX_WAIT_TIME = 120  # 最长等待时间（秒）
    CHECK_INTERVAL = 2  # 检查间隔（秒）

    def __init__(
        self,
        browser: BrowserManager,
        solver=None,  # 保留参数兼容性，但不使用
        account_id: Optional[str] = None
    ):
        """
        初始化处理器

        Args:
            browser: 浏览器管理器
            solver: 验证码求解器（2.0 版本不使用，由插件处理）
            account_id: 账号标识（用于日志）
        """
        self.browser = browser
        self.solver = solver  # 不使用，仅保持接口兼容
        self._logger = get_logger(__name__, account_id=account_id)

    def _get_handler_name(self) -> str:
        return "Turnstile"

    def _get_post_inject_delay(self) -> float:
        return 1.0

    async def detect(self) -> bool:
        """
        检测页面是否存在 Turnstile

        Returns:
            是否存在 Turnstile
        """
        page = self.browser.page

        # 检查 iframe
        iframe = await page.query_selector(self.SELECTORS["iframe"])
        if iframe:
            self._logger.info("检测到 Turnstile iframe")
            return True

        # 检查容器
        container = await page.query_selector(self.SELECTORS["container"])
        if container:
            self._logger.info("检测到 Turnstile 容器")
            return True

        # 通过 frame URL 检测（适配 shadow DOM / iframe 不可直接选择）
        for frame in page.frames:
            url = frame.url or ""
            if "challenges.cloudflare.com" in url or "turnstile" in url:
                self._logger.info("检测到 Turnstile frame")
                return True

        return False

    async def _check_solved(self) -> bool:
        """
        检查 Turnstile 是否已由插件解决

        Returns:
            是否已解决
        """
        page = self.browser.page

        # 检查响应输入框是否有值
        try:
            has_response = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                return input && input.value && input.value.length > 0;
            }''')
            if has_response:
                return True
        except Exception:
            pass

        # 检查成功指示器
        success = await page.query_selector(self.SELECTORS["success_indicator"])
        if success:
            return True

        # 如果 Turnstile frame 仍存在，视为未通过
        for frame in page.frames:
            url = frame.url or ""
            if "challenges.cloudflare.com" in url or "turnstile" in url:
                return False

        # 检查 iframe 是否消失（验证完成后通常会消失）
        iframe = await page.query_selector(self.SELECTORS["iframe"])
        container = await page.query_selector(self.SELECTORS["container"])
        if not iframe and not container:
            return True

        return False

    async def _try_click_checkbox(self) -> bool:
        """尝试点击 Turnstile 复选框区域（跨域 iframe 只能点坐标）"""
        page = self.browser.page

        try:
            iframe = await page.query_selector(self.SELECTORS["iframe"])
            if iframe:
                box = await iframe.bounding_box()
                if box:
                    click_x = box["x"] + min(35, box["width"] * 0.2)
                    click_y = box["y"] + box["height"] / 2
                    await page.mouse.click(click_x, click_y)
                    return True
        except Exception:
            pass

        try:
            container = await page.query_selector(self.SELECTORS["container"])
            if container:
                box = await container.bounding_box()
                if box:
                    click_x = box["x"] + box["width"] / 2
                    click_y = box["y"] + box["height"] / 2
                    await page.mouse.click(click_x, click_y)
                    return True
        except Exception:
            pass

        # 通过 frame 位置点击（适配 shadow DOM / iframe 不可直接选择）
        try:
            for frame in page.frames:
                url = frame.url or ""
                if "challenges.cloudflare.com" in url or "turnstile" in url:
                    frame_el = await frame.frame_element()
                    if frame_el:
                        box = await frame_el.bounding_box()
                        if box:
                            click_x = box["x"] + min(35, box["width"] * 0.2)
                            click_y = box["y"] + box["height"] / 2
                            await page.mouse.click(click_x, click_y)
                            return True
        except Exception:
            pass

        return False

    async def _extract_params(self) -> bool:
        """提取验证码参数（2.0 版本由插件处理，始终返回 True）"""
        return True

    async def _inject_token(self, token: str) -> bool:
        """注入 token（2.0 版本由插件处理，无需手动注入）"""
        return True

    async def _solve_captcha(self) -> str:
        """调用求解 API（2.0 版本由插件处理，返回空字符串）"""
        return ""

    async def solve(self) -> Tuple[bool, Optional[str]]:
        """
        等待 Turnstile 验证完成（由插件处理）

        Returns:
            (是否成功, 错误信息)
        """
        self._logger.info("等待 YesCaptcha 插件处理 Turnstile...")

        if await self._try_click_checkbox():
            self._logger.debug("已尝试点击 Turnstile 复选框")

        elapsed = 0
        while elapsed < self.MAX_WAIT_TIME:
            if await self._check_solved():
                self._logger.info("Turnstile 验证已完成")
                return True, None

            await asyncio.sleep(self.CHECK_INTERVAL)
            elapsed += self.CHECK_INTERVAL

            if elapsed % 10 == 0:
                self._logger.debug(f"等待 Turnstile 完成... ({elapsed}/{self.MAX_WAIT_TIME}s)")
                await self._try_click_checkbox()

        self._logger.error(f"Turnstile 验证超时 ({self.MAX_WAIT_TIME}s)")
        return False, f"Turnstile 验证超时（{self.MAX_WAIT_TIME}秒）"


async def handle_turnstile(
    browser: BrowserManager,
    solver=None,
    account_id: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    处理 Turnstile（便捷函数）

    Args:
        browser: 浏览器管理器
        solver: 验证码求解器（2.0 版本不使用）
        account_id: 账号标识

    Returns:
        (是否成功, 错误信息)
    """
    handler = TurnstileHandler(browser, solver, account_id)

    if not await handler.detect():
        return True, None  # 无需处理

    return await handler.solve()
