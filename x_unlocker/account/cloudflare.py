"""
Cloudflare 检测与处理模块

功能:
- 检测 Cloudflare 阻塞（空白页/JS 挑战）
- 处理 Cloudflare Turnstile 验证
- 处理 Cloudflare JS 挑战
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..core.browser import BrowserManager
    from ..captcha.solver import CaptchaSolver


class CloudflareHandler:
    """Cloudflare 检测与处理器"""

    def __init__(
        self,
        browser: "BrowserManager",
        solver: Optional["CaptchaSolver"] = None,
        account_id: Optional[str] = None
    ):
        """
        初始化处理器

        Args:
            browser: 浏览器管理器
            solver: 验证码求解器（用于 Turnstile）
            account_id: 账号标识（用于日志）
        """
        self.browser = browser
        self.solver = solver
        self._logger = get_logger(__name__, account_id=account_id)

    async def check_cloudflare_block(self) -> bool:
        """
        检测页面是否被 Cloudflare 阻塞（空白页/JS 挑战）

        Returns:
            True 表示被阻塞，False 表示正常
        """
        page = self.browser.page

        try:
            # 确保页面 DOM 加载完成
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except:
                pass

            # 获取页面内容长度
            body_text_length = await page.evaluate("document.body?.innerText?.length || 0")
            body_html_length = await page.evaluate("document.body?.innerHTML?.length || 0")

            self._logger.debug(f"页面检测: innerText={body_text_length}, innerHTML={body_html_length}")

            # 情况 1: 完全空白页面（内容极少）
            if body_text_length < 20 and body_html_length < 200:
                self._logger.warning("检测到空白页面 - 可能被 Cloudflare 阻塞")
                return True

            # 情况 2: 检查是否有 Cloudflare 相关特征（增强版）
            cf_indicators = await page.evaluate("""() => {
                const html = document.documentElement.outerHTML.toLowerCase();
                return {
                    // Cloudflare 标识检测
                    hasCloudflare: html.includes('cloudflare') || html.includes('cf-ray') || html.includes('cf-chl'),
                    // JS 挑战特征
                    hasJsChallenge: html.includes('jschl') || html.includes('ray id:'),
                    // 人机验证文本
                    hasVerify: html.includes('verify you are human') || html.includes('checking your browser'),
                    // DOM 元素检测（增强）
                    hasChallengeForm: !!document.querySelector('#challenge-form, [name="cf_chl_jschl_tk"], .challenge-platform'),
                    // Turnstile iframe 检测
                    hasTurnstileIframe: !!document.querySelector('iframe[src*="challenges.cloudflare.com"]'),
                    // Turnstile 容器检测
                    hasTurnstileContainer: !!document.querySelector('.cf-turnstile, [data-sitekey]'),
                    // 页面标题
                    title: document.title.toLowerCase(),
                    // 页面文本长度（用于判断是否为挑战页面）
                    bodyLength: document.body?.innerText?.length || 0
                };
            }""")

            self._logger.debug(f"Cloudflare 特征检测: {cf_indicators}")

            # 检查标题是否包含 Cloudflare 相关内容
            cf_titles = ['just a moment', 'attention required', 'please wait', 'checking your browser']
            for cf_title in cf_titles:
                if cf_title in cf_indicators.get('title', ''):
                    self._logger.warning(f"检测到 Cloudflare 挑战页面 (标题: {cf_indicators['title']})")
                    return True

            # 检测到 challenge-form 或 challenge-platform
            if cf_indicators.get('hasChallengeForm'):
                self._logger.warning("检测到 Cloudflare 挑战表单")
                return True

            # 检测到 Turnstile iframe（明确的 Cloudflare 验证）
            if cf_indicators.get('hasTurnstileIframe'):
                self._logger.warning("检测到 Cloudflare Turnstile iframe")
                return True

            # 只有同时检测到 Cloudflare 标识和挑战特征时才认为被阻塞
            if cf_indicators.get('hasCloudflare') and cf_indicators.get('hasJsChallenge'):
                self._logger.warning("检测到 Cloudflare JS 挑战")
                return True

            if cf_indicators.get('hasVerify'):
                self._logger.warning("检测到 Cloudflare 人机验证")
                return True

            return False

        except Exception as e:
            self._logger.debug(f"Cloudflare 检测出错: {e}")
            return False

    async def check_and_solve_turnstile(self) -> bool:
        """
        检测并处理 Cloudflare Turnstile

        Returns:
            是否成功（无 Turnstile 或已解决）
        """
        if not self.solver:
            self._logger.debug("未提供验证码求解器，使用插件等待模式处理 Turnstile")

        # 延迟导入避免循环依赖
        from ..captcha.turnstile import TurnstileHandler

        handler = TurnstileHandler(
            browser=self.browser,
            solver=self.solver,
            account_id=self._logger.name
        )

        # 尝试多次检测（插件模式更长等待）
        max_attempts = 15 if not self.solver else 3
        for attempt in range(max_attempts):
            self._logger.debug(f"Turnstile 检测尝试 {attempt + 1}/{max_attempts}")

            if await handler.detect():
                self._logger.info("检测到 Cloudflare Turnstile，开始求解...")

                # 截图记录 Turnstile 页面
                try:
                    from pathlib import Path
                    output_dir = Path("output/debug")
                    output_dir.mkdir(parents=True, exist_ok=True)
                    await self.browser.page.screenshot(
                        path=str(output_dir / f"turnstile_detected.png")
                    )
                except:
                    pass

                success, error = await handler.solve()

                if success:
                    self._logger.info("Turnstile 求解成功")
                    await asyncio.sleep(2)  # 等待页面刷新
                    return True
                else:
                    self._logger.error(f"Turnstile 求解失败: {error}")
                    return False

            await asyncio.sleep(2)

        # 未检测到 Turnstile，进入后续等待逻辑
        self._logger.warning("未检测到 Turnstile，继续等待 Cloudflare")
        return False

    async def handle_cloudflare_block(self) -> bool:
        """
        处理 Cloudflare 阻塞

        Returns:
            是否成功处理
        """
        self._logger.info("尝试处理 Cloudflare 阻塞...")

        # 首先尝试 Turnstile 处理
        if await self.check_and_solve_turnstile():
            # 等待页面刷新
            await asyncio.sleep(3)

            # 检查是否仍被阻塞
            if not await self.check_cloudflare_block():
                self._logger.info("Cloudflare 阻塞已解除")
                return True

        # 如果 Turnstile 无效，尝试简单等待（有时 JS 挑战会自动完成）
        self._logger.info("等待 Cloudflare JS 挑战自动完成（最长 60 秒）...")
        for wait_attempt in range(12):
            await asyncio.sleep(5)  # 每次等待 5 秒，总计 60 秒

            # 检查页面状态
            if not await self.check_cloudflare_block():
                self._logger.info(f"Cloudflare 挑战已自动完成 (等待 {(wait_attempt + 1) * 5} 秒)")
                return True

            self._logger.debug(f"等待 Cloudflare 挑战... ({wait_attempt + 1}/12)")

        self._logger.error("无法解除 Cloudflare 阻塞")
        return False
