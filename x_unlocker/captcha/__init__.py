"""
Captcha 模块 - 验证码处理

支持的服务:
- 2captcha (默认)
- CapMonster Cloud
- FunBypass (专门针对 FunCaptcha)

使用方式:
    # 使用工厂函数创建求解器（推荐）
    from x_unlocker.captcha import create_solver
    solver = create_solver(config.captcha)

    # 直接使用特定求解器
    from x_unlocker.captcha.solver import CaptchaSolver
    from x_unlocker.captcha.capmonster_solver import CapMonsterSolver
    from x_unlocker.captcha.funbypass_solver import FunBypassSolver

    # 验证码处理器
    from x_unlocker.captcha.turnstile import TurnstileHandler
    from x_unlocker.captcha.arkose import ArkoseHandler
"""

# 2captcha 求解器
from .solver import CaptchaSolver, CaptchaSolverError, create_solver as create_2captcha_solver

# CapMonster Cloud 求解器
from .capmonster_solver import CapMonsterSolver, create_capmonster_solver

# FunBypass 求解器（专门针对 FunCaptcha）
from .funbypass_solver import FunBypassSolver, create_funbypass_solver

# 工厂函数（推荐使用）
from .factory import (
    CaptchaSolverProtocol,
    create_solver,
    create_solver_with_balance_check,
)

__all__ = [
    # 求解器协议
    "CaptchaSolverProtocol",

    # 工厂函数
    "create_solver",
    "create_solver_with_balance_check",

    # 2captcha
    "CaptchaSolver",
    "CaptchaSolverError",
    "create_2captcha_solver",

    # CapMonster
    "CapMonsterSolver",
    "create_capmonster_solver",

    # FunBypass
    "FunBypassSolver",
    "create_funbypass_solver",
]
