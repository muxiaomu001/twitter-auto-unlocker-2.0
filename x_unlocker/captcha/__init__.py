"""
Captcha 模块 - 验证码处理 (2.0 版本)

支持的服务:
- YesCaptcha 人机助手插件（推荐）
- YesCaptcha API

使用方式:
    # 使用工厂函数创建求解器（推荐）
    from x_unlocker.captcha import create_solver, CaptchaConfig
    config = CaptchaConfig(api_key="your_key")
    solver = create_solver(config)

    # 验证码处理器
    from x_unlocker.captcha.turnstile import TurnstileHandler
    from x_unlocker.captcha.arkose import ArkoseHandler
"""

# YesCaptcha 求解器
from .yescaptcha_solver import YesCaptchaSolver

# 工厂函数（推荐使用）
from .factory import (
    CaptchaConfig,
    CaptchaSolverProtocol,
    create_solver,
    create_solver_with_balance_check,
    is_plugin_mode,
)

__all__ = [
    # 配置
    "CaptchaConfig",

    # 求解器协议
    "CaptchaSolverProtocol",

    # 工厂函数
    "create_solver",
    "create_solver_with_balance_check",
    "is_plugin_mode",

    # YesCaptcha
    "YesCaptchaSolver",
]
