"""
验证码处理器基类模块

提供 Turnstile 和 Arkose 处理器的统一抽象接口，
使用模板方法模式统一求解流程。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, Tuple

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..core.browser import BrowserManager
    from .yescaptcha_solver import YesCaptchaSolver


class BaseCaptchaHandler(ABC):
    """验证码处理器抽象基类"""

    def __init__(
        self,
        browser: "BrowserManager",
        solver: "YesCaptchaSolver",
        account_id: Optional[str] = None
    ):
        """
        初始化处理器

        Args:
            browser: 浏览器管理器
            solver: 验证码求解器
            account_id: 账号标识（用于日志）
        """
        self.browser = browser
        self.solver = solver
        self._logger = get_logger(__name__, account_id=account_id)

    @abstractmethod
    async def detect(self) -> bool:
        """
        检测验证码是否存在

        Returns:
            是否检测到验证码
        """
        pass

    @abstractmethod
    async def _extract_params(self) -> bool:
        """
        提取验证码参数（内部方法）

        Returns:
            是否成功提取
        """
        pass

    @abstractmethod
    async def _inject_token(self, token: str) -> bool:
        """
        注入验证 token（内部方法）

        Args:
            token: 验证 token

        Returns:
            是否成功注入
        """
        pass

    @abstractmethod
    async def _solve_captcha(self) -> str:
        """
        调用具体的求解 API

        Returns:
            验证 token

        Raises:
            CaptchaSolverError: 求解失败
        """
        pass

    def _get_handler_name(self) -> str:
        """获取处理器名称（用于日志）"""
        return self.__class__.__name__

    def _get_post_inject_delay(self) -> float:
        """
        获取注入后等待时间（秒）

        子类可覆盖此方法调整等待时间

        Returns:
            等待时间（秒）
        """
        return 1.0

    async def solve(self) -> Tuple[bool, Optional[str]]:
        """
        完整的验证码求解流程（模板方法）

        Returns:
            (是否成功, 错误信息)
        """
        handler_name = self._get_handler_name()
        self._logger.info(f"开始处理 {handler_name}")

        # 1. 提取参数
        if not await self._extract_params():
            return False, f"无法提取 {handler_name} 参数"

        # 2. 调用求解 API
        try:
            token = await self._solve_captcha()
        except Exception as e:
            error_msg = str(e)
            self._logger.error(f"{handler_name} 求解失败: {error_msg}")
            return False, error_msg

        # 3. 注入 token
        if not await self._inject_token(token):
            # 即使注入"失败"，也继续尝试，因为某些方法可能已生效
            self._logger.warning(f"{handler_name} Token 注入返回失败，但继续尝试")

        # 4. 等待验证完成
        await asyncio.sleep(self._get_post_inject_delay())

        self._logger.info(f"{handler_name} 处理完成")
        return True, None
