"""
Arkose Labs FunCaptcha 处理模块 (图像识别版本)

功能:
- 检测页面中的 Arkose 验证码
- 截取六宫格图片
- 提取问题文本
- 调用 YesCaptcha 图像识别 API
- 根据结果模拟点击

版本: 2.0 - 使用图像识别+模拟点击方式
"""

import asyncio
import base64
from typing import Optional, Tuple, List
from dataclasses import dataclass

from .base import BaseCaptchaHandler
from .yescaptcha_solver import YesCaptchaSolver, YesCaptchaSolverError
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FunCaptchaState:
    """FunCaptcha 状态数据"""
    detected: bool = False
    question: str = ""
    image_count: int = 6  # 默认六宫格
    current_round: int = 0
    max_rounds: int = 10  # 最大验证轮数


class ArkoseHandler(BaseCaptchaHandler):
    """
    Arkose Labs FunCaptcha 处理器（图像识别版本）

    使用流程:
    1. 检测 FunCaptcha iframe
    2. 进入 iframe 上下文
    3. 截取六宫格图片
    4. 获取问题文本
    5. 调用 YesCaptcha 图像识别
    6. 根据返回索引模拟点击
    7. 等待结果，如需要则重复步骤 3-6
    """

    # FunCaptcha 相关选择器
    SELECTORS = {
        # iframe 选择器
        "iframe": 'iframe[src*="arkoselabs"], iframe[src*="funcaptcha"], iframe[id*="arkose"], iframe[title*="arkose"]',
        # 挑战容器
        "challenge_container": "#fc-iframe-wrap, .fc-dialog",
        # 问题文本
        "question": "#game-header h2, .game-header h2, [data-string-id]",
        # 六宫格图片区域
        "image_grid": ".game ul, #game ul, .game-container ul",
        # 单个图片项
        "image_item": ".game ul li, #game ul li, .game-container ul li img",
        # 验证按钮
        "verify_button": "#verify, button[type='submit'], .verify-button",
        # 成功标记
        "success": ".success-message, #success, [data-success]",
        # 失败/重试标记
        "retry": ".retry-message, #retry, .challenge-error",
    }

    # 六宫格布局 (2x3 或 3x2)
    GRID_POSITIONS = [
        (0, 0), (1, 0), (2, 0),  # 第一行
        (0, 1), (1, 1), (2, 1),  # 第二行
    ]

    def __init__(
        self,
        browser,  # BrowserManager or Page
        solver: YesCaptchaSolver,
        account_id: Optional[str] = None
    ):
        """
        初始化处理器

        Args:
            browser: 浏览器管理器或 Page 对象
            solver: YesCaptcha 图像识别求解器
            account_id: 账号标识（用于日志）
        """
        super().__init__(browser, solver, account_id)
        self.yescaptcha_solver = solver
        self._state = FunCaptchaState()
        self._challenge_frame = None

    def _get_handler_name(self) -> str:
        return "Arkose FunCaptcha (图像识别)"

    def _get_post_inject_delay(self) -> float:
        return 1.5  # 点击后等待时间

    async def detect(self) -> bool:
        """
        检测页面是否存在 Arkose FunCaptcha

        Returns:
            是否存在 Arkose
        """
        page = self._get_page()

        try:
            # 检查 iframe
            iframe = await page.query_selector(self.SELECTORS["iframe"])
            if iframe:
                self._logger.info("检测到 Arkose iframe")
                self._state.detected = True
                return True

            # 检查容器
            container = await page.query_selector(self.SELECTORS["challenge_container"])
            if container:
                self._logger.info("检测到 Arkose 挑战容器")
                self._state.detected = True
                return True

            # 检查页面内容中的 Arkose 标记
            content = await page.content()
            if "arkoselabs" in content.lower() or "funcaptcha" in content.lower():
                self._logger.info("检测到 Arkose 相关内容")
                self._state.detected = True
                return True

        except Exception as e:
            self._logger.warning(f"检测 Arkose 时出错: {e}")

        return False

    def _get_page(self):
        """获取 page 对象"""
        if hasattr(self.browser, 'page'):
            return self.browser.page
        return self.browser

    async def _get_challenge_frame(self):
        """获取挑战 iframe 的 frame 对象"""
        page = self._get_page()

        try:
            # 等待 iframe 出现
            await page.wait_for_selector(self.SELECTORS["iframe"], timeout=10000)

            # 获取 iframe 元素
            iframe = await page.query_selector(self.SELECTORS["iframe"])
            if not iframe:
                self._logger.warning("未找到 Arkose iframe")
                return None

            # 获取 frame 内容
            frame = await iframe.content_frame()
            if not frame:
                self._logger.warning("无法获取 iframe 内容")
                return None

            self._challenge_frame = frame
            return frame

        except Exception as e:
            self._logger.error(f"获取挑战 frame 失败: {e}")
            return None

    async def _extract_question(self, frame) -> Optional[str]:
        """
        提取问题文本

        Args:
            frame: iframe 的 frame 对象

        Returns:
            问题文本，如 "Pick the lion"
        """
        try:
            # 尝试多个选择器
            selectors = [
                "#game-header h2",
                ".game-header h2",
                "[data-string-id]",
                ".instruction-text",
                "#instructions",
            ]

            for selector in selectors:
                element = await frame.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text:
                        text = text.strip()
                        self._logger.info(f"提取到问题文本: {text}")
                        return text

            # 尝试 JavaScript 提取
            question = await frame.evaluate('''() => {
                // 尝试多种方式获取问题文本
                const selectors = [
                    '#game-header h2',
                    '.game-header h2',
                    '[data-string-id]',
                    '.instruction-text',
                    '#instructions'
                ];

                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.textContent) {
                        return el.textContent.trim();
                    }
                }

                return null;
            }''')

            if question:
                self._logger.info(f"通过 JS 提取到问题文本: {question}")
                return question

        except Exception as e:
            self._logger.warning(f"提取问题文本失败: {e}")

        return None

    async def _capture_image_grid(self, frame) -> Optional[bytes]:
        """
        截取六宫格图片区域

        Args:
            frame: iframe 的 frame 对象

        Returns:
            图片的字节数据
        """
        try:
            # 等待图片加载
            await asyncio.sleep(0.5)

            # 尝试多个选择器定位图片区域
            selectors = [
                "#game ul",
                ".game ul",
                ".game-container ul",
                "#fc-iframe-wrap ul",
                ".image-grid",
            ]

            for selector in selectors:
                element = await frame.query_selector(selector)
                if element:
                    # 截取元素截图
                    screenshot = await element.screenshot()
                    self._logger.info(f"成功截取图片区域 ({selector})")
                    return screenshot

            # 如果找不到特定区域，截取整个 frame
            self._logger.warning("未找到图片区域选择器，截取整个挑战区域")
            screenshot = await frame.screenshot()
            return screenshot

        except Exception as e:
            self._logger.error(f"截取图片失败: {e}")
            return None

    async def _click_image_at_index(self, frame, index: int) -> bool:
        """
        点击指定索引的图片

        Args:
            frame: iframe 的 frame 对象
            index: 从 0 开始的图片索引

        Returns:
            是否点击成功
        """
        try:
            # 获取所有图片项
            items = await frame.query_selector_all(self.SELECTORS["image_item"])

            if not items:
                # 尝试其他选择器
                items = await frame.query_selector_all("#game ul li, .game ul li")

            if not items:
                self._logger.error("未找到图片项")
                return False

            if index >= len(items):
                self._logger.error(f"索引 {index} 超出范围 (共 {len(items)} 项)")
                return False

            # 点击目标图片
            target = items[index]
            await target.click()
            self._logger.info(f"点击了索引 {index} 的图片")

            # 等待响应
            await asyncio.sleep(0.5)
            return True

        except Exception as e:
            self._logger.error(f"点击图片失败: {e}")
            return False

    async def _click_verify_button(self, frame) -> bool:
        """点击验证按钮"""
        try:
            button = await frame.query_selector(self.SELECTORS["verify_button"])
            if button:
                await button.click()
                self._logger.info("点击了验证按钮")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            self._logger.warning(f"点击验证按钮失败: {e}")
        return False

    async def _check_challenge_result(self, frame) -> Tuple[bool, bool]:
        """
        检查挑战结果

        Returns:
            (is_complete, is_success)
            - is_complete: 挑战是否结束
            - is_success: 是否成功通过
        """
        try:
            # 检查成功标记
            success = await frame.query_selector(self.SELECTORS["success"])
            if success:
                return True, True

            # 检查是否需要重试
            retry = await frame.query_selector(self.SELECTORS["retry"])
            if retry:
                return True, False

            # 检查是否有新的问题（继续下一轮）
            question = await self._extract_question(frame)
            if question and question != self._state.question:
                self._state.question = question
                return False, False  # 继续下一轮

            return False, False

        except Exception as e:
            self._logger.warning(f"检查结果时出错: {e}")
            return False, False

    async def _solve_single_round(self, frame) -> bool:
        """
        解决单轮验证

        Args:
            frame: iframe 的 frame 对象

        Returns:
            是否成功
        """
        self._state.current_round += 1
        self._logger.info(f"开始第 {self._state.current_round} 轮验证")

        # 1. 提取问题文本
        question = await self._extract_question(frame)
        if not question:
            self._logger.error("无法提取问题文本")
            return False

        self._state.question = question

        # 2. 截取图片
        image_bytes = await self._capture_image_grid(frame)
        if not image_bytes:
            self._logger.error("无法截取图片")
            return False

        # 3. 转换为 Base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # 4. 调用 YesCaptcha API
        try:
            result = await self.yescaptcha_solver.solve_funcaptcha_classification(
                image_base64=image_base64,
                question=question
            )

            if not result.success:
                self._logger.error(f"YesCaptcha 识别失败: {result.error_description}")
                return False

            # 5. 点击识别结果
            for idx in result.objects:
                success = await self._click_image_at_index(frame, idx)
                if not success:
                    return False
                await asyncio.sleep(0.3)  # 点击间隔

            return True

        except YesCaptchaSolverError as e:
            self._logger.error(f"YesCaptcha API 错误: {e}")
            return False

    async def solve(self) -> Tuple[bool, Optional[str]]:
        """
        执行完整的验证码求解流程

        Returns:
            (是否成功, 错误信息)
        """
        self._logger.info("开始求解 Arkose FunCaptcha (图像识别模式)")

        # 获取挑战 frame
        frame = await self._get_challenge_frame()
        if not frame:
            return False, "无法获取挑战 iframe"

        # 循环解决多轮验证
        while self._state.current_round < self._state.max_rounds:
            # 解决当前轮
            success = await self._solve_single_round(frame)

            if not success:
                self._logger.warning(f"第 {self._state.current_round} 轮验证失败")
                # 可能需要重试
                await asyncio.sleep(1)
                continue

            # 等待并检查结果
            await asyncio.sleep(1.5)

            is_complete, is_success = await self._check_challenge_result(frame)

            if is_complete:
                if is_success:
                    self._logger.info(f"Arkose FunCaptcha 验证成功 (共 {self._state.current_round} 轮)")
                    return True, None
                else:
                    self._logger.warning("验证失败，需要重试")
                    # 重置轮数继续尝试
                    continue

            # 检查 iframe 是否还存在（可能已经成功关闭）
            page = self._get_page()
            iframe_exists = await page.query_selector(self.SELECTORS["iframe"])
            if not iframe_exists:
                self._logger.info("Arkose iframe 已消失，验证可能已成功")
                return True, None

            # 继续下一轮
            await asyncio.sleep(0.5)

        return False, f"超过最大验证轮数 ({self._state.max_rounds})"


async def handle_arkose(
    browser,
    solver: YesCaptchaSolver,
    account_id: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    处理 Arkose FunCaptcha（便捷函数）

    Args:
        browser: 浏览器管理器或 Page 对象
        solver: YesCaptcha 图像识别求解器
        account_id: 账号标识

    Returns:
        (是否成功, 错误信息)
    """
    handler = ArkoseHandler(browser, solver, account_id)

    if not await handler.detect():
        return True, None  # 无需处理

    return await handler.solve()
