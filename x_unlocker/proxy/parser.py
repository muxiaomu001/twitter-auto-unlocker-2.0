"""
代理解析模块 - 解析 SOCKS5 代理字符串

支持格式: ip:端口:用户名:密码
"""

from dataclasses import dataclass
from typing import Optional

from ..core.errors import ProxyParseError as BaseProxyParseError


@dataclass
class ProxyConfig:
    """代理配置"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    @property
    def server(self) -> str:
        """返回 socks5://host:port 格式"""
        return f"socks5://{self.host}:{self.port}"

    @property
    def playwright_proxy(self) -> dict:
        """返回 Playwright/Camoufox 代理配置格式"""
        proxy = {"server": self.server}
        if self.username:
            proxy["username"] = self.username
        if self.password:
            proxy["password"] = self.password
        return proxy

    def __str__(self) -> str:
        """返回脱敏的代理字符串"""
        if self.username:
            return f"socks5://{self.username}:***@{self.host}:{self.port}"
        return self.server


# 使用统一异常模型，保持向后兼容
ProxyParseError = BaseProxyParseError


def parse_proxy(proxy_str: str) -> ProxyConfig:
    """
    解析代理字符串

    Args:
        proxy_str: 代理字符串，格式为 ip:端口:用户名:密码

    Returns:
        ProxyConfig 对象

    Raises:
        ProxyParseError: 解析失败时抛出
    """
    if not proxy_str or not proxy_str.strip():
        raise ProxyParseError("代理字符串不能为空")

    proxy_str = proxy_str.strip()
    parts = proxy_str.split(":")

    if len(parts) < 2:
        raise ProxyParseError(
            f"代理格式错误: {proxy_str}，期望格式: ip:端口[:用户名:密码]"
        )

    host = parts[0].strip()
    if not host:
        raise ProxyParseError("代理主机地址不能为空")

    try:
        port = int(parts[1].strip())
        if not (1 <= port <= 65535):
            raise ValueError("端口范围错误")
    except ValueError:
        raise ProxyParseError(f"代理端口无效: {parts[1]}")

    username = None
    password = None

    if len(parts) >= 4:
        username = parts[2].strip() or None
        password = parts[3].strip() or None
    elif len(parts) == 3:
        # 只有用户名没有密码的情况
        username = parts[2].strip() or None

    return ProxyConfig(
        host=host,
        port=port,
        username=username,
        password=password
    )


def validate_proxy(proxy_str: str) -> bool:
    """
    验证代理字符串格式是否正确

    Args:
        proxy_str: 代理字符串

    Returns:
        True 如果格式正确，否则 False
    """
    try:
        parse_proxy(proxy_str)
        return True
    except ProxyParseError:
        return False
