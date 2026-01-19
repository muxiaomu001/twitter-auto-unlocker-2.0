"""
验证码求解器工厂 (2.0 版本)

功能:
- 根据配置创建 YesCaptcha 图像识别求解器
- 支持插件模式（推荐）和 API 模式

版本: 2.0 - 仅支持 YesCaptcha
"""

from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass

from .yescaptcha_solver import YesCaptchaSolver
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CaptchaConfig:
    """验证码配置（简化版）"""
    mode: str = "plugin"  # "plugin" 或 "api"
    api_key: str = ""
    timeout: int = 30
    max_retries: int = 3
    max_rounds: int = 10


@runtime_checkable
class CaptchaSolverProtocol(Protocol):
    """
    验证码求解器协议

    所有求解器实现必须符合此协议接口
    """

    async def solve_funcaptcha_classification(
        self,
        image_base64: str,
        question: str
    ):
        """求解 FunCaptcha 图像识别"""
        ...

    async def get_balance(self) -> float:
        """查询账户余额"""
        ...


def create_solver(config: CaptchaConfig) -> YesCaptchaSolver:
    """
    创建 YesCaptcha 图像识别求解器

    Args:
        config: 验证码配置对象

    Returns:
        YesCaptchaSolver 实例

    Raises:
        ValueError: API Key 未配置
    """
    if not config.api_key:
        raise ValueError("YesCaptcha API Key 未配置")

    logger.info(f"创建 YesCaptcha 求解器 (mode={config.mode}, timeout={config.timeout}s)")

    return YesCaptchaSolver(
        api_key=config.api_key,
        timeout=config.timeout,
        max_retries=config.max_retries
    )


async def create_solver_with_balance_check(
    config: CaptchaConfig,
    min_balance: float = 10.0  # POINTS
) -> YesCaptchaSolver:
    """
    创建求解器并检查余额

    Args:
        config: 验证码配置
        min_balance: 最小余额警告阈值（POINTS）

    Returns:
        求解器实例
    """
    solver = create_solver(config)

    try:
        balance = await solver.get_balance()

        if balance < min_balance:
            logger.warning(f"YesCaptcha 余额不足: {balance:.0f} POINTS，建议充值")
        else:
            logger.info(f"YesCaptcha 余额: {balance:.0f} POINTS")

    except Exception as e:
        logger.warning(f"无法检查 YesCaptcha 余额: {e}")

    return solver


def is_plugin_mode(config: CaptchaConfig) -> bool:
    """
    检查是否使用插件模式

    Args:
        config: 验证码配置

    Returns:
        是否使用插件模式
    """
    return config.mode.lower() == "plugin"


__all__ = [
    "CaptchaConfig",
    "CaptchaSolverProtocol",
    "create_solver",
    "create_solver_with_balance_check",
    "is_plugin_mode",
]
