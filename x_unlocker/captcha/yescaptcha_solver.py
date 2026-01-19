"""
YesCaptcha 图像识别求解器

使用 YesCaptcha 的 FunCaptchaClassification API 进行图像识别。
该 API 直接返回结果（无需轮询），适用于 Arkose FunCaptcha 的六宫格图像识别。

API 文档: https://yescaptcha.atlassian.net/wiki/spaces/YESCAPTCHA/pages/34209793
"""

import asyncio
import base64
from dataclasses import dataclass
from typing import List, Optional
import aiohttp

from x_unlocker.utils.logger import get_logger

logger = get_logger(__name__)


# API 常量
API_ENDPOINT = "https://api.yescaptcha.com/createTask"
TASK_TYPE_FUNCAPTCHA_CLASSIFICATION = "FunCaptchaClassification"


@dataclass
class FunCaptchaResult:
    """FunCaptcha 图像识别结果"""
    success: bool
    objects: List[int]  # 从 0 开始的索引列表
    error_id: int = 0
    error_code: str = ""
    error_description: str = ""


class YesCaptchaSolverError(Exception):
    """YesCaptcha 求解器错误"""
    pass


class YesCaptchaSolver:
    """
    YesCaptcha 图像识别求解器

    使用 FunCaptchaClassification API 识别六宫格图片中的正确选项。

    使用示例:
        solver = YesCaptchaSolver(api_key="YOUR_API_KEY")
        result = await solver.solve_funcaptcha_classification(
            image_base64="...",
            question="Pick the lion"
        )
        if result.success:
            click_index = result.objects[0]  # 从 0 开始
    """

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        初始化 YesCaptcha 求解器

        Args:
            api_key: YesCaptcha API Key
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """关闭 HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def solve_funcaptcha_classification(
        self,
        image_base64: str,
        question: str
    ) -> FunCaptchaResult:
        """
        使用图像识别求解 FunCaptcha

        Args:
            image_base64: 六宫格图片的 Base64 编码（不含 data:image/... 前缀）
            question: 原始问题文本（如 "Pick the lion"）

        Returns:
            FunCaptchaResult: 包含识别结果的对象

        Raises:
            YesCaptchaSolverError: API 调用失败
        """
        # 清理 base64 前缀
        if image_base64.startswith("data:"):
            # 移除 data:image/png;base64, 前缀
            image_base64 = image_base64.split(",", 1)[1]

        # 构建请求
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": TASK_TYPE_FUNCAPTCHA_CLASSIFICATION,
                "image": image_base64,
                "question": question
            }
        }

        logger.info(f"调用 YesCaptcha API，问题: {question}")

        # 重试逻辑
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = await self._call_api(payload)
                return result
            except YesCaptchaSolverError as e:
                last_error = e
                logger.warning(f"YesCaptcha API 调用失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)

        raise YesCaptchaSolverError(f"YesCaptcha API 调用失败，已重试 {self.max_retries} 次: {last_error}")

    async def _call_api(self, payload: dict) -> FunCaptchaResult:
        """
        调用 YesCaptcha API

        Args:
            payload: 请求体

        Returns:
            FunCaptchaResult: API 响应结果
        """
        session = await self._get_session()

        try:
            async with session.post(API_ENDPOINT, json=payload) as response:
                data = await response.json()

                logger.debug(f"YesCaptcha API 响应: {data}")

                error_id = data.get("errorId", 0)

                if error_id != 0:
                    error_code = data.get("errorCode", "UNKNOWN")
                    error_desc = data.get("errorDescription", "未知错误")
                    logger.error(f"YesCaptcha API 错误: [{error_code}] {error_desc}")
                    return FunCaptchaResult(
                        success=False,
                        objects=[],
                        error_id=error_id,
                        error_code=error_code,
                        error_description=error_desc
                    )

                # 解析成功响应
                solution = data.get("solution", {})
                objects = solution.get("objects", [])

                if not objects:
                    logger.warning("YesCaptcha 返回空的 objects 列表")
                    return FunCaptchaResult(
                        success=False,
                        objects=[],
                        error_code="EMPTY_RESULT",
                        error_description="API 返回空结果"
                    )

                logger.info(f"YesCaptcha 识别成功，结果索引: {objects}")
                return FunCaptchaResult(
                    success=True,
                    objects=objects
                )

        except aiohttp.ClientError as e:
            raise YesCaptchaSolverError(f"HTTP 请求失败: {e}")
        except Exception as e:
            raise YesCaptchaSolverError(f"API 调用异常: {e}")

    async def get_balance(self) -> float:
        """
        查询账户余额

        Returns:
            float: 账户余额（POINTS）
        """
        payload = {
            "clientKey": self.api_key
        }

        session = await self._get_session()

        try:
            async with session.post(
                "https://api.yescaptcha.com/getBalance",
                json=payload
            ) as response:
                data = await response.json()

                error_id = data.get("errorId", 0)
                if error_id != 0:
                    error_desc = data.get("errorDescription", "未知错误")
                    raise YesCaptchaSolverError(f"查询余额失败: {error_desc}")

                balance = data.get("balance", 0)
                logger.info(f"YesCaptcha 账户余额: {balance} POINTS")
                return balance

        except aiohttp.ClientError as e:
            raise YesCaptchaSolverError(f"查询余额失败: {e}")


def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    将图片字节编码为 Base64 字符串

    Args:
        image_bytes: 图片的字节数据

    Returns:
        str: Base64 编码的字符串
    """
    return base64.b64encode(image_bytes).decode("utf-8")
