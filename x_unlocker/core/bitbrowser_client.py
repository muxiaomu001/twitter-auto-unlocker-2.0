"""
BitBrowser Client - 比特浏览器 HTTP API 客户端

通过 HTTP API 与比特浏览器进行交互：
- 创建/删除浏览器配置
- 打开/关闭浏览器窗口
- 获取 WebSocket 调试端口

API 文档: https://doc.bitbrowser.cn/
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import aiohttp

from ..proxy.parser import ProxyConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BitBrowserConfig:
    """比特浏览器配置"""
    api_url: str = "http://127.0.0.1:54345"
    open_timeout: int = 30  # 打开浏览器超时时间（秒）
    request_timeout: int = 10  # API 请求超时时间（秒）


class BitBrowserError(Exception):
    """比特浏览器 API 错误"""
    pass


class BitBrowserClient:
    """
    比特浏览器 HTTP API 客户端

    用于与比特浏览器客户端进行交互，支持：
    - 动态创建浏览器配置
    - 打开/关闭浏览器窗口
    - 获取 WebSocket 调试端口用于 Playwright 连接
    """

    def __init__(self, config: Optional[BitBrowserConfig] = None):
        """
        初始化客户端

        Args:
            config: 比特浏览器配置，默认使用本地默认端口
        """
        self.config = config or BitBrowserConfig()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送 API 请求

        Args:
            method: HTTP 方法
            endpoint: API 端点
            data: 请求数据
            timeout: 超时时间（秒）

        Returns:
            API 响应数据

        Raises:
            BitBrowserError: API 调用失败
        """
        session = await self._get_session()
        url = f"{self.config.api_url}{endpoint}"
        timeout_val = timeout or self.config.request_timeout

        try:
            async with session.request(
                method,
                url,
                json=data,
                timeout=aiohttp.ClientTimeout(total=timeout_val)
            ) as response:
                result = await response.json()

                # 检查 API 响应
                if not result.get("success", False):
                    error_msg = result.get("msg", "Unknown error")
                    raise BitBrowserError(f"API 错误: {error_msg}")

                return result

        except aiohttp.ClientError as e:
            raise BitBrowserError(f"API 请求失败: {e}")
        except Exception as e:
            if isinstance(e, BitBrowserError):
                raise
            raise BitBrowserError(f"请求异常: {e}")

    async def create_browser(
        self,
        name: Optional[str] = None,
        proxy: Optional[ProxyConfig] = None,
        remark: str = "Auto created by x-unlocker"
    ) -> str:
        """
        创建新的浏览器配置

        Args:
            name: 浏览器名称（自动生成如不指定）
            proxy: 代理配置
            remark: 备注

        Returns:
            浏览器 ID

        Raises:
            BitBrowserError: 创建失败
        """
        if not name:
            name = f"x-unlock-{uuid.uuid4().hex[:8]}"

        # 构建浏览器配置
        # BitBrowser API 参数说明参考: https://doc.bitbrowser.cn/api-jie-kou-wen-dang/liu-lan-qi-jie-kou
        #
        # 重要：browserFingerPrint 必传，传空对象 {} 表示随机指纹
        # 注意：groupId 对于主账号可以不传，传 "0" 反而会报错
        browser_config: Dict[str, Any] = {
            "name": name,
            "remark": remark,
            # 指纹配置 - 传空对象让 BitBrowser 自动生成随机指纹
            "browserFingerPrint": {}
        }

        # 配置代理 - proxyMethod 和 proxyType 是顶级字段
        # proxyMethod: 2=自定义代理（默认）, 3=提取IP
        # proxyType: 'noproxy', 'http', 'https', 'socks5', '911s5'
        if proxy:
            browser_config["proxyMethod"] = 2  # 2=自定义代理
            browser_config["proxyType"] = "socks5"
            browser_config["host"] = proxy.host
            browser_config["port"] = str(proxy.port)
            if proxy.username:
                browser_config["proxyUserName"] = proxy.username
            if proxy.password:
                browser_config["proxyPassword"] = proxy.password
        else:
            browser_config["proxyMethod"] = 2  # 2=自定义代理（默认）
            browser_config["proxyType"] = "noproxy"

        logger.info(f"创建 BitBrowser 配置: {name}")

        result = await self._request("POST", "/browser/update", browser_config)
        browser_id = result.get("data", {}).get("id")

        if not browser_id:
            raise BitBrowserError("API 返回中缺少浏览器 ID")

        logger.info(f"BitBrowser 配置已创建: {browser_id}")
        return browser_id

    async def open_browser(self, browser_id: str) -> str:
        """
        打开浏览器窗口并返回 WebSocket 调试端口

        Args:
            browser_id: 浏览器 ID

        Returns:
            WebSocket endpoint URL

        Raises:
            BitBrowserError: 打开失败
        """
        logger.info(f"打开 BitBrowser 窗口: {browser_id}")

        result = await self._request(
            "POST",
            "/browser/open",
            {"id": browser_id},
            timeout=self.config.open_timeout
        )

        ws_endpoint = result.get("data", {}).get("ws")
        if not ws_endpoint:
            raise BitBrowserError("API 返回中缺少 ws 字段")

        logger.info(f"BitBrowser 窗口已打开，WS: {ws_endpoint[:50]}...")
        return ws_endpoint

    async def close_browser(self, browser_id: str) -> bool:
        """
        关闭浏览器窗口

        Args:
            browser_id: 浏览器 ID

        Returns:
            是否成功关闭
        """
        logger.info(f"关闭 BitBrowser 窗口: {browser_id}")

        try:
            await self._request("POST", "/browser/close", {"id": browser_id})
            logger.info(f"BitBrowser 窗口已关闭: {browser_id}")
            return True
        except BitBrowserError as e:
            logger.warning(f"关闭浏览器窗口失败: {e}")
            return False

    async def delete_browser(self, browser_id: str) -> bool:
        """
        删除浏览器配置

        Args:
            browser_id: 浏览器 ID

        Returns:
            是否成功删除
        """
        logger.info(f"删除 BitBrowser 配置: {browser_id}")

        try:
            await self._request("POST", "/browser/delete", {"id": browser_id})
            logger.info(f"BitBrowser 配置已删除: {browser_id}")
            return True
        except BitBrowserError as e:
            logger.warning(f"删除浏览器配置失败: {e}")
            return False

    async def check_connection(self) -> bool:
        """
        检查与 BitBrowser 的连接

        Returns:
            是否连接正常
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.config.api_url}/",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
        except Exception:
            return False
