"""
统一异常模型模块

功能:
- 定义领域异常层级结构
- 区分可重试与致命错误
- 提供统一的错误分类信号

异常层级:
    XUnlockerError (基类)
    ├── ConfigError (配置错误 - 不可重试)
    ├── AuthError (认证错误)
    │   ├── LoginFailedError (登录失败 - 可重试)
    │   ├── AccountSuspendedError (账号封禁 - 不可重试)
    │   └── TwoFactorError (2FA 错误 - 不可重试)
    ├── CaptchaError (验证码错误)
    │   ├── CaptchaDetectionError (检测失败 - 可重试)
    │   └── CaptchaSolveError (求解失败 - 可重试)
    ├── NetworkError (网络错误 - 可重试)
    │   ├── TimeoutError (超时)
    │   └── ConnectionError (连接错误)
    ├── BrowserError (浏览器错误)
    │   ├── BrowserStartError (启动失败 - 可重试)
    │   └── PageNavigationError (导航失败 - 可重试)
    └── SessionError (会话错误 - 不可重试)
"""

from enum import Enum
from typing import Optional


class ErrorCategory(Enum):
    """错误分类"""
    CONFIG = "config"           # 配置错误
    AUTH = "auth"               # 认证错误
    CAPTCHA = "captcha"         # 验证码错误
    NETWORK = "network"         # 网络错误
    BROWSER = "browser"         # 浏览器错误
    SESSION = "session"         # 会话错误
    UNKNOWN = "unknown"         # 未知错误


class XUnlockerError(Exception):
    """
    基础异常类

    所有项目异常的父类，提供统一的属性接口。

    Attributes:
        message: 错误消息
        category: 错误分类
        retryable: 是否可重试
        cause: 原始异常（如有）
    """

    category: ErrorCategory = ErrorCategory.UNKNOWN
    retryable: bool = False

    def __init__(
        self,
        message: str = "",
        *,
        cause: Optional[Exception] = None,
        retryable: Optional[bool] = None
    ):
        """
        初始化异常

        Args:
            message: 错误消息
            cause: 原始异常
            retryable: 覆盖默认的可重试标志
        """
        super().__init__(message)
        self.message = message
        self.cause = cause
        if retryable is not None:
            self.retryable = retryable

    def __str__(self) -> str:
        base = self.message or self.__class__.__name__
        if self.cause:
            return f"{base} (原因: {self.cause})"
        return base

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"category={self.category.value}, "
            f"retryable={self.retryable})"
        )


# ============================================================================
# 配置错误 (不可重试)
# ============================================================================

class ConfigError(XUnlockerError):
    """
    配置错误

    当配置无效或缺失时抛出。
    通常不可重试，需要用户修复配置。
    """
    category = ErrorCategory.CONFIG
    retryable = False


class MissingConfigError(ConfigError):
    """必需配置项缺失"""
    pass


class InvalidConfigError(ConfigError):
    """配置值无效"""
    pass


# ============================================================================
# 认证错误
# ============================================================================

class AuthError(XUnlockerError):
    """
    认证错误基类

    登录、2FA、异常活动验证等相关错误。
    """
    category = ErrorCategory.AUTH
    retryable = True  # 默认可重试


class LoginFailedError(AuthError):
    """
    登录失败

    用户名/密码错误或登录流程异常。
    可重试（可能是临时问题）。
    """
    retryable = True


class AccountSuspendedError(AuthError):
    """
    账号已封禁

    账号被永久封禁，无法解锁。
    不可重试。
    """
    retryable = False


class AccountLockedError(AuthError):
    """
    账号已锁定

    账号需要解锁流程处理。
    可重试。
    """
    retryable = True


class TwoFactorError(AuthError):
    """
    2FA 验证错误

    TOTP 密钥无效或验证码生成失败。
    通常不可重试（密钥问题）。
    """
    retryable = False


class UnusualActivityError(AuthError):
    """
    异常活动验证失败

    Twitter 检测到异常活动，验证步骤失败。
    可重试。
    """
    retryable = True


class CloudflareBlockedError(AuthError):
    """
    被 Cloudflare 阻止

    IP 被 Cloudflare 阻止或 JS 挑战失败。
    可重试（换代理后可能成功）。
    """
    retryable = True


# ============================================================================
# 验证码错误
# ============================================================================

class CaptchaError(XUnlockerError):
    """
    验证码错误基类

    验证码检测、求解相关错误。
    """
    category = ErrorCategory.CAPTCHA
    retryable = True  # 验证码错误通常可重试


class CaptchaDetectionError(CaptchaError):
    """
    验证码检测失败

    无法检测到验证码类型或参数。
    可重试。
    """
    retryable = True


class CaptchaSolveError(CaptchaError):
    """
    验证码求解失败

    调用验证码服务失败或 token 无效。
    可重试。
    """
    retryable = True


class CaptchaInjectError(CaptchaError):
    """
    验证码 token 注入失败

    token 注入到页面失败。
    可重试。
    """
    retryable = True


class CaptchaServiceError(CaptchaError):
    """
    验证码服务错误

    2captcha 等服务不可用或余额不足。
    不可重试（需要充值或更换服务）。
    """
    retryable = False


# ============================================================================
# 网络错误 (可重试)
# ============================================================================

class NetworkError(XUnlockerError):
    """
    网络错误基类

    网络连接、超时等错误。
    通常可重试。
    """
    category = ErrorCategory.NETWORK
    retryable = True


class ConnectionTimeoutError(NetworkError):
    """连接超时"""
    retryable = True


class RequestFailedError(NetworkError):
    """请求失败"""
    retryable = True


class ProxyError(NetworkError):
    """
    代理错误

    代理连接失败或认证失败。
    可重试（换代理可能成功）。
    """
    retryable = True


# ============================================================================
# 浏览器错误
# ============================================================================

class BrowserError(XUnlockerError):
    """
    浏览器错误基类

    Camoufox 浏览器相关错误。
    """
    category = ErrorCategory.BROWSER
    retryable = True


class BrowserStartError(BrowserError):
    """浏览器启动失败"""
    retryable = True


class BrowserNotStartedError(BrowserError):
    """浏览器未启动"""
    retryable = False


class PageNavigationError(BrowserError):
    """页面导航失败"""
    retryable = True


class PageLoadError(BrowserError):
    """页面加载失败"""
    retryable = True


class ElementNotFoundError(BrowserError):
    """页面元素未找到"""
    retryable = True


class BitBrowserError(BrowserError):
    """
    比特浏览器错误

    BitBrowser API 调用失败或连接错误。
    可重试（服务可能临时不可用）。
    """
    retryable = True


# ============================================================================
# 会话错误
# ============================================================================

class SessionError(XUnlockerError):
    """
    会话错误基类

    Cookie 保存、会话管理等错误。
    """
    category = ErrorCategory.SESSION
    retryable = False


class CookieSaveError(SessionError):
    """Cookie 保存失败"""
    retryable = False


class SessionExpiredError(SessionError):
    """会话已过期"""
    retryable = True  # 可以重新登录


# ============================================================================
# 解析错误 (向后兼容)
# ============================================================================

class ParseError(XUnlockerError):
    """
    解析错误基类

    账号、代理等解析错误。
    """
    category = ErrorCategory.CONFIG
    retryable = False


class AccountParseError(ParseError):
    """
    账号解析错误

    保持与现有代码兼容，但扩展了基类属性。
    """

    def __init__(
        self,
        message: str,
        line_number: Optional[int] = None,
        line_content: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.line_number = line_number
        self.line_content = line_content

    def __str__(self) -> str:
        if self.line_number:
            return f"第 {self.line_number} 行: {self.message}"
        return self.message


class ProxyParseError(ParseError):
    """代理解析错误"""
    pass


# ============================================================================
# 工具函数
# ============================================================================

def is_retryable(error: Exception) -> bool:
    """
    判断错误是否可重试

    Args:
        error: 异常实例

    Returns:
        是否可重试
    """
    if isinstance(error, XUnlockerError):
        return error.retryable

    # 对于非项目异常，根据类型判断
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(error, (ValueError, TypeError, AttributeError)):
        return False

    # 默认不重试
    return False


def get_error_category(error: Exception) -> ErrorCategory:
    """
    获取错误分类

    Args:
        error: 异常实例

    Returns:
        错误分类
    """
    if isinstance(error, XUnlockerError):
        return error.category
    return ErrorCategory.UNKNOWN


def wrap_exception(
    error: Exception,
    error_class: type[XUnlockerError],
    message: Optional[str] = None
) -> XUnlockerError:
    """
    包装异常为项目异常

    Args:
        error: 原始异常
        error_class: 目标异常类
        message: 自定义消息（可选）

    Returns:
        包装后的异常
    """
    msg = message or str(error)
    return error_class(msg, cause=error)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 枚举
    "ErrorCategory",

    # 基类
    "XUnlockerError",

    # 配置错误
    "ConfigError",
    "MissingConfigError",
    "InvalidConfigError",

    # 认证错误
    "AuthError",
    "LoginFailedError",
    "AccountSuspendedError",
    "AccountLockedError",
    "TwoFactorError",
    "UnusualActivityError",
    "CloudflareBlockedError",

    # 验证码错误
    "CaptchaError",
    "CaptchaDetectionError",
    "CaptchaSolveError",
    "CaptchaInjectError",
    "CaptchaServiceError",

    # 网络错误
    "NetworkError",
    "ConnectionTimeoutError",
    "RequestFailedError",
    "ProxyError",

    # 浏览器错误
    "BrowserError",
    "BrowserStartError",
    "BrowserNotStartedError",
    "PageNavigationError",
    "PageLoadError",
    "ElementNotFoundError",
    "BitBrowserError",

    # 会话错误
    "SessionError",
    "CookieSaveError",
    "SessionExpiredError",

    # 解析错误
    "ParseError",
    "AccountParseError",
    "ProxyParseError",

    # 工具函数
    "is_retryable",
    "get_error_category",
    "wrap_exception",
]
