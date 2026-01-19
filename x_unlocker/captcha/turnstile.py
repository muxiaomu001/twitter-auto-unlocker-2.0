"""
Cloudflare Turnstile 处理模块

功能:
- 检测页面中的 Turnstile 验证码
- 提取 sitekey
- 调用 2captcha 求解
- 注入 token
"""

import asyncio
import re
from typing import Optional, Tuple

from .base import BaseCaptchaHandler
from .solver import CaptchaSolver, CaptchaSolverError
from ..core.browser import BrowserManager
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TurnstileHandler(BaseCaptchaHandler):
    """Cloudflare Turnstile 处理器"""

    # Turnstile 相关选择器
    SELECTORS = {
        "iframe": 'iframe[src*="challenges.cloudflare.com"]',
        "container": '.cf-turnstile, [data-sitekey]',
        "response_input": 'input[name="cf-turnstile-response"]',
    }

    def __init__(
        self,
        browser: BrowserManager,
        solver: CaptchaSolver,
        account_id: Optional[str] = None
    ):
        """
        初始化处理器

        Args:
            browser: 浏览器管理器
            solver: 验证码求解器
            account_id: 账号标识（用于日志）
        """
        super().__init__(browser, solver, account_id)
        self._sitekey: Optional[str] = None
        self._page_url: Optional[str] = None
        self._action: Optional[str] = None
        self._cdata: Optional[str] = None

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

        return False

    async def _extract_sitekey(self) -> Optional[str]:
        """
        提取 Turnstile sitekey

        Returns:
            sitekey 或 None
        """
        page = self.browser.page

        # 方法 1: 从 data-sitekey 属性提取
        container = await page.query_selector('[data-sitekey]')
        if container:
            sitekey = await container.get_attribute('data-sitekey')
            if sitekey:
                self._logger.debug(f"从 data-sitekey 提取: {sitekey}")
                return sitekey

        # 方法 2: 从 iframe src 提取
        iframe = await page.query_selector(self.SELECTORS["iframe"])
        if iframe:
            src = await iframe.get_attribute('src')
            if src:
                match = re.search(r'sitekey=([a-zA-Z0-9_-]+)', src)
                if match:
                    sitekey = match.group(1)
                    self._logger.debug(f"从 iframe src 提取: {sitekey}")
                    return sitekey

        # 方法 3: 从页面脚本提取
        try:
            sitekey = await page.evaluate('''() => {
                // 检查全局变量
                if (window.turnstileKey) return window.turnstileKey;
                if (window.cfSiteKey) return window.cfSiteKey;

                // 检查脚本内容
                const scripts = document.querySelectorAll('script');
                for (const script of scripts) {
                    const content = script.textContent || '';
                    const match = content.match(/sitekey['\":\\s]+['\"]?([a-zA-Z0-9_-]{30,})/);
                    if (match) return match[1];
                }

                return null;
            }''')
            if sitekey:
                self._logger.debug(f"从脚本提取: {sitekey}")
                return sitekey
        except Exception as e:
            self._logger.debug(f"脚本提取失败: {e}")

        self._logger.warning("无法提取 Turnstile sitekey")
        return None

    async def _extract_params(self) -> bool:
        """提取验证码参数（增强版：包含 action 和 cdata）"""
        self._sitekey = await self._extract_sitekey()
        if not self._sitekey:
            return False

        self._page_url = self.browser.page.url
        page = self.browser.page

        # 提取 action 和 cdata 参数
        try:
            params = await page.evaluate("""() => {
                // 从容器属性提取
                const container = document.querySelector('.cf-turnstile, [data-sitekey]');
                if (container) {
                    return {
                        action: container.getAttribute('data-action'),
                        cdata: container.getAttribute('data-cdata')
                    };
                }
                // 从 iframe src 提取
                const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (iframe) {
                    try {
                        const url = new URL(iframe.src);
                        return {
                            action: url.searchParams.get('action'),
                            cdata: url.searchParams.get('data')
                        };
                    } catch(e) {}
                }
                return {};
            }""")

            self._action = params.get('action')
            self._cdata = params.get('cdata')

            if self._action:
                self._logger.debug(f"提取到 action: {self._action}")
            if self._cdata:
                self._logger.debug(f"提取到 cdata: {self._cdata[:30]}...")

        except Exception as e:
            self._logger.debug(f"提取 action/cdata 失败: {e}")
            self._action = None
            self._cdata = None

        return True

    async def _inject_token(self, token: str) -> bool:
        """
        注入 Turnstile token（增强版：触发事件并尝试提交）

        Args:
            token: 验证 token

        Returns:
            是否成功
        """
        page = self.browser.page

        try:
            result = await page.evaluate('''(token) => {
                // 方法 1: 设置隐藏输入框并触发事件
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                if (input) {
                    input.value = token;
                    // 触发事件（重要！有些页面依赖这些事件）
                    ['input', 'change'].forEach(ev =>
                        input.dispatchEvent(new Event(ev, {bubbles: true}))
                    );
                    // 尝试提交表单
                    const form = input.form || input.closest('form');
                    if (form) {
                        try {
                            form.submit();
                            return 'input+submit';
                        } catch(e) {
                            return 'input';
                        }
                    }
                    return 'input';
                }

                // 方法 2: 调用回调函数
                const container = document.querySelector('.cf-turnstile, [data-sitekey]');
                if (container) {
                    const callback = container.getAttribute('data-callback');
                    if (callback && typeof window[callback] === 'function') {
                        window[callback](token);
                        return 'callback';
                    }
                }

                // 方法 3: 使用 Turnstile API（如果可用）
                if (window.turnstile) {
                    // 尝试 setResponse（新版 API）
                    if (typeof window.turnstile.setResponse === 'function') {
                        try {
                            window.turnstile.setResponse(token);
                            return 'setResponse';
                        } catch(e) {}
                    }
                    // 触发自定义事件
                    const event = new CustomEvent('turnstile-callback', {
                        detail: { token: token }
                    });
                    document.dispatchEvent(event);
                    return 'event';
                }

                // 方法 4: 创建隐藏输入框（如果不存在）
                const newInput = document.createElement('input');
                newInput.type = 'hidden';
                newInput.name = 'cf-turnstile-response';
                newInput.value = token;
                const anyForm = document.querySelector('form');
                if (anyForm) {
                    anyForm.appendChild(newInput);
                    return 'created';
                }

                return null;
            }''', token)

            if result:
                self._logger.info(f"Token 注入成功 (方式: {result})")
                return True

        except Exception as e:
            self._logger.error(f"Token 注入失败: {e}")

        return False

    async def _solve_captcha(self) -> str:
        """调用 2captcha 求解 Turnstile（增强版：传递 action/cdata）"""
        return await self.solver.solve_turnstile(
            sitekey=self._sitekey,
            page_url=self._page_url,
            action=self._action,
            data=self._cdata
        )

    # 保持向后兼容的公开方法
    async def extract_sitekey(self) -> Optional[str]:
        """提取 Turnstile sitekey（公开方法，保持向后兼容）"""
        return await self._extract_sitekey()

    async def inject_token(self, token: str) -> bool:
        """注入 Turnstile token（公开方法，保持向后兼容）"""
        return await self._inject_token(token)


async def handle_turnstile(
    browser: BrowserManager,
    solver: CaptchaSolver,
    account_id: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    处理 Turnstile（便捷函数）

    Args:
        browser: 浏览器管理器
        solver: 验证码求解器
        account_id: 账号标识

    Returns:
        (是否成功, 错误信息)
    """
    handler = TurnstileHandler(browser, solver, account_id)

    if not await handler.detect():
        return True, None  # 无需处理

    return await handler.solve()
