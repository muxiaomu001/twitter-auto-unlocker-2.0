"""
通用工具函数模块

提供:
- 人类行为模拟延迟
- 指数退避计算
- 安全截图封装
- 页面加载等待
"""

import asyncio
import logging
import random
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

# 默认延迟常量
HUMAN_DELAY_MIN = 0.5
HUMAN_DELAY_MAX = 1.5


async def human_delay(
    min_delay: float = HUMAN_DELAY_MIN,
    max_delay: float = HUMAN_DELAY_MAX
) -> float:
    """
    模拟人类操作的随机延迟

    Args:
        min_delay: 最小延迟（秒）
        max_delay: 最大延迟（秒）

    Returns:
        实际延迟时间（秒）

    Example:
        await human_delay()  # 默认 0.5-1.5 秒
        await human_delay(1, 3)  # 自定义 1-3 秒
    """
    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)
    return delay


def exponential_backoff(
    attempt: int,
    base: float = 5.0,
    max_delay: float = 300.0,
    jitter: bool = True
) -> float:
    """
    计算指数退避延迟时间

    Args:
        attempt: 当前尝试次数（从 1 开始）
        base: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        jitter: 是否添加随机抖动

    Returns:
        延迟时间（秒）

    Example:
        delay = exponential_backoff(1)  # 5 秒
        delay = exponential_backoff(2)  # 10 秒
        delay = exponential_backoff(3)  # 20 秒
    """
    # 计算指数延迟: base * 2^(attempt-1)
    delay = base * (2 ** (attempt - 1))

    # 限制最大延迟
    delay = min(delay, max_delay)

    # 添加随机抖动（±25%）
    if jitter:
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


async def wait_for_backoff(
    attempt: int,
    base: float = 5.0,
    max_delay: float = 300.0,
    logger: Optional[logging.Logger] = None
) -> float:
    """
    执行指数退避等待

    Args:
        attempt: 当前尝试次数（从 1 开始）
        base: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        logger: 日志记录器（可选）

    Returns:
        实际等待时间（秒）

    Example:
        await wait_for_backoff(2, logger=logger)  # 等待约 10 秒
    """
    delay = exponential_backoff(attempt, base, max_delay)

    if logger:
        logger.info(f"等待 {delay:.1f} 秒后重试（第 {attempt} 次尝试）")

    await asyncio.sleep(delay)
    return delay


async def safe_screenshot(
    page: "Page",
    path: Union[str, Path],
    full_page: bool = False,
    logger: Optional[logging.Logger] = None
) -> bool:
    """
    安全地保存页面截图

    捕获所有异常，确保截图失败不会中断主流程。

    Args:
        page: Playwright 页面对象
        path: 截图保存路径
        full_page: 是否截取整页
        logger: 日志记录器（可选）

    Returns:
        是否成功

    Example:
        success = await safe_screenshot(page, "debug.png")
    """
    try:
        # 确保目录存在
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 等待短暂时间确保渲染完成
        await asyncio.sleep(0.3)

        # 截图
        await page.screenshot(path=str(path), full_page=full_page)

        if logger:
            logger.debug(f"截图已保存: {path}")

        return True

    except Exception as e:
        if logger:
            logger.warning(f"截图保存失败: {e}")
        return False


async def wait_for_network_idle(
    page: "Page",
    timeout: int = 10000,
    logger: Optional[logging.Logger] = None
) -> bool:
    """
    等待页面网络空闲

    安全地等待页面网络请求完成，超时不抛异常。

    Args:
        page: Playwright 页面对象
        timeout: 超时时间（毫秒）
        logger: 日志记录器（可选）

    Returns:
        是否成功（超时返回 False）

    Example:
        await wait_for_network_idle(page, timeout=15000)
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
        if logger:
            logger.debug("页面网络空闲")
        return True
    except Exception as e:
        if logger:
            logger.debug(f"等待网络空闲超时: {e}")
        return False


async def wait_for_page_load(
    page: "Page",
    state: str = "domcontentloaded",
    timeout: int = 30000,
    logger: Optional[logging.Logger] = None
) -> bool:
    """
    等待页面加载完成

    安全地等待页面加载，超时不抛异常。

    Args:
        page: Playwright 页面对象
        state: 加载状态 ("load", "domcontentloaded", "networkidle")
        timeout: 超时时间（毫秒）
        logger: 日志记录器（可选）

    Returns:
        是否成功（超时返回 False）

    Example:
        await wait_for_page_load(page, state="networkidle")
    """
    try:
        await page.wait_for_load_state(state, timeout=timeout)
        if logger:
            logger.debug(f"页面加载完成: {state}")
        return True
    except Exception as e:
        if logger:
            logger.debug(f"等待页面加载超时 ({state}): {e}")
        return False


async def retry_with_backoff(
    func,
    max_attempts: int = 3,
    base_delay: float = 5.0,
    retryable_exceptions: tuple = (Exception,),
    logger: Optional[logging.Logger] = None
):
    """
    使用指数退避重试异步函数

    Args:
        func: 要执行的异步函数（无参数或已绑定参数）
        max_attempts: 最大尝试次数
        base_delay: 基础延迟（秒）
        retryable_exceptions: 可重试的异常类型
        logger: 日志记录器（可选）

    Returns:
        函数返回值

    Raises:
        最后一次尝试的异常

    Example:
        result = await retry_with_backoff(
            lambda: fetch_data(),
            max_attempts=3,
            retryable_exceptions=(ConnectionError, TimeoutError)
        )
    """
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e
            if logger:
                logger.warning(f"尝试 {attempt}/{max_attempts} 失败: {e}")

            if attempt < max_attempts:
                await wait_for_backoff(attempt, base_delay, logger=logger)

    # 所有尝试都失败，抛出最后一个异常
    raise last_exception


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    将值限制在指定范围内

    Args:
        value: 输入值
        min_val: 最小值
        max_val: 最大值

    Returns:
        限制后的值

    Example:
        clamp(15, 0, 10)  # 返回 10
        clamp(-5, 0, 10)  # 返回 0
    """
    return max(min_val, min(value, max_val))


def safe_filename(name: str, max_length: int = 100) -> str:
    """
    将字符串转换为安全的文件名

    Args:
        name: 原始字符串
        max_length: 最大长度

    Returns:
        安全的文件名

    Example:
        safe_filename("user@name:123")  # 返回 "user_name_123"
    """
    # 替换不安全字符
    unsafe_chars = '<>:"/\\|?*@'
    result = name
    for char in unsafe_chars:
        result = result.replace(char, '_')

    # 去除首尾空白
    result = result.strip()

    # 限制长度
    if len(result) > max_length:
        result = result[:max_length]

    return result or "unnamed"


__all__ = [
    # 常量
    "HUMAN_DELAY_MIN",
    "HUMAN_DELAY_MAX",
    # 延迟函数
    "human_delay",
    "exponential_backoff",
    "wait_for_backoff",
    # 页面操作
    "safe_screenshot",
    "wait_for_network_idle",
    "wait_for_page_load",
    # 重试
    "retry_with_backoff",
    # 工具函数
    "clamp",
    "safe_filename",
]
