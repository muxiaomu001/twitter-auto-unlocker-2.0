"""
Core 模块 - 核心流程控制

使用方式:
    from x_unlocker.core.browser import BrowserManager, create_browser
    from x_unlocker.core.session import SessionManager
    from x_unlocker.core.unlock_flow import UnlockFlow, unlock_account
    from x_unlocker.core.errors import XUnlockerError, is_retryable
    from x_unlocker.core.config import AppConfig, load_config
"""

# 导出错误类（不会引起循环依赖）
from .errors import (
    XUnlockerError,
    ErrorCategory,
    is_retryable,
    get_error_category,
)

# 导出配置类
from .config import (
    AppConfig,
    load_config,
)

__all__ = [
    # 错误
    "XUnlockerError",
    "ErrorCategory",
    "is_retryable",
    "get_error_category",
    # 配置
    "AppConfig",
    "load_config",
]
