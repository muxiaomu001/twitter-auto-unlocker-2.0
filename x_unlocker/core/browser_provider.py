"""
Browser Provider - 浏览器提供者抽象基类

定义浏览器自动化的统一接口，支持多种浏览器后端实现。

Providers:
- CamoufoxProvider: 使用 Camoufox (Firefox 内核) 的本地浏览器
- BitBrowserProvider: 使用比特浏览器 API 的远程浏览器
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Any


class BrowserProviderType(Enum):
    """浏览器提供者类型"""
    CAMOUFOX = "camoufox"
    BITBROWSER = "bitbrowser"


class BrowserProvider(ABC):
    """
    浏览器提供者抽象基类

    定义所有浏览器实现必须提供的接口。
    所有方法都是异步的，支持 asyncio 并发。
    """

    @abstractmethod
    async def start(self) -> "BrowserProvider":
        """
        启动/连接浏览器

        Returns:
            self, 用于链式调用
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭浏览器连接并清理资源"""
        pass

    @property
    @abstractmethod
    def page(self) -> Any:
        """
        获取当前页面对象 (Playwright Page)

        Raises:
            BrowserNotStartedError: 浏览器未启动
        """
        pass

    @property
    @abstractmethod
    def context(self) -> Any:
        """
        获取浏览器上下文 (Playwright BrowserContext)

        Raises:
            BrowserNotStartedError: 浏览器未启动
        """
        pass

    @abstractmethod
    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        """
        导航到指定 URL

        Args:
            url: 目标 URL
            wait_until: 等待条件 (domcontentloaded, load, networkidle)
        """
        pass

    @abstractmethod
    async def screenshot(
        self,
        path: str,
        full_page: bool = False,
        wait_before: float = 0.5
    ) -> None:
        """
        保存页面截图

        Args:
            path: 截图保存路径
            full_page: 是否截取完整页面
            wait_before: 截图前等待时间（秒）
        """
        pass

    @abstractmethod
    async def wait_for_selector(
        self,
        selector: str,
        timeout: Optional[int] = None,
        state: str = "visible"
    ) -> Any:
        """
        等待元素出现

        Args:
            selector: CSS 选择器
            timeout: 超时时间（毫秒）
            state: 等待状态 (attached, detached, visible, hidden)

        Returns:
            元素句柄
        """
        pass

    @abstractmethod
    async def type_text(
        self,
        selector: str,
        text: str,
        delay: int = 50
    ) -> None:
        """
        在元素中输入文本（模拟人类输入）

        Args:
            selector: CSS 选择器
            text: 要输入的文本
            delay: 字符间延迟（毫秒）
        """
        pass

    @abstractmethod
    async def click(self, selector: str, wait_after: float = 0.5) -> None:
        """
        点击元素

        Args:
            selector: CSS 选择器
            wait_after: 点击后等待时间（秒）
        """
        pass

    @abstractmethod
    async def get_user_agent(self) -> Optional[str]:
        """
        获取当前浏览器的 User-Agent

        Returns:
            User-Agent 字符串或 None
        """
        pass
