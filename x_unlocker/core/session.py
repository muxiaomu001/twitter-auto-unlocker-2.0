"""
会话管理模块 - Cookie 导出与管理

功能:
- 从浏览器导出 cookies
- 保存/加载 cookies 到 JSON 文件
- Cookie 格式转换
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from ..core.browser import BrowserManager
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """会话管理器"""

    def __init__(self, output_dir: Path):
        """
        初始化会话管理器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)

    def _get_account_dir(self, account_id: str) -> Path:
        """获取账号输出目录"""
        account_dir = self.output_dir / account_id
        account_dir.mkdir(parents=True, exist_ok=True)
        return account_dir

    async def save_cookies(
        self,
        browser: BrowserManager,
        account_id: str
    ) -> Path:
        """
        保存浏览器 cookies 到文件

        Args:
            browser: 浏览器管理器
            account_id: 账号标识

        Returns:
            cookies 文件路径
        """
        account_dir = self._get_account_dir(account_id)
        cookies_file = account_dir / "cookies.json"

        # 获取 cookies
        cookies = await browser.context.cookies()

        # 添加元数据
        data = {
            "account_id": account_id,
            "exported_at": datetime.now().isoformat(),
            "cookies": cookies
        }

        # 保存到文件
        async with aiofiles.open(cookies_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

        logger.info(f"Cookies 已保存到: {cookies_file}")
        return cookies_file

    async def load_cookies(
        self,
        browser: BrowserManager,
        account_id: str
    ) -> bool:
        """
        从文件加载 cookies 到浏览器

        Args:
            browser: 浏览器管理器
            account_id: 账号标识

        Returns:
            是否成功加载
        """
        cookies_file = self.output_dir / account_id / "cookies.json"

        if not cookies_file.exists():
            logger.warning(f"Cookies 文件不存在: {cookies_file}")
            return False

        try:
            async with aiofiles.open(cookies_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

            cookies = data.get("cookies", [])
            if cookies:
                await browser.context.add_cookies(cookies)
                logger.info(f"已加载 {len(cookies)} 个 cookies")
                return True
            else:
                logger.warning("Cookies 文件为空")
                return False

        except Exception as e:
            logger.error(f"加载 cookies 失败: {e}")
            return False

    async def save_screenshot(
        self,
        browser: BrowserManager,
        account_id: str,
        name: str
    ) -> Path:
        """
        保存截图

        Args:
            browser: 浏览器管理器
            account_id: 账号标识
            name: 截图名称（不含扩展名）

        Returns:
            截图文件路径
        """
        account_dir = self._get_account_dir(account_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_file = account_dir / f"screenshot_{name}_{timestamp}.png"

        await browser.screenshot(str(screenshot_file))
        logger.debug(f"截图已保存: {screenshot_file}")

        return screenshot_file

    async def save_result(
        self,
        account_id: str,
        success: bool,
        message: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        保存解锁结果

        Args:
            account_id: 账号标识
            success: 是否成功
            message: 结果消息
            extra_data: 额外数据

        Returns:
            结果文件路径
        """
        account_dir = self._get_account_dir(account_id)
        result_file = account_dir / "result.json"

        data = {
            "account_id": account_id,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **(extra_data or {})
        }

        async with aiofiles.open(result_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

        logger.info(f"结果已保存: {result_file}")
        return result_file


def get_twitter_cookies(cookies: List[Dict]) -> Dict[str, str]:
    """
    提取 Twitter 关键 cookies

    Args:
        cookies: 完整 cookies 列表

    Returns:
        关键 cookies 字典
    """
    key_cookies = ["auth_token", "ct0", "twid", "kdt"]
    result = {}

    for cookie in cookies:
        name = cookie.get("name", "")
        if name in key_cookies:
            result[name] = cookie.get("value", "")

    return result


def cookies_to_header_string(cookies: List[Dict]) -> str:
    """
    将 cookies 转换为 Cookie 请求头格式

    Args:
        cookies: cookies 列表

    Returns:
        Cookie 头字符串
    """
    parts = []
    for cookie in cookies:
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        if name and value:
            parts.append(f"{name}={value}")

    return "; ".join(parts)
