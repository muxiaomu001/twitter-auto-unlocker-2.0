"""
计时器工具模块

功能:
- 上下文管理器风格的计时器
- 自动记录操作耗时到日志
- 支持结构化日志字段
"""

import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, Optional
import logging


@contextmanager
def timed(
    logger: logging.Logger,
    operation: str,
    level: int = logging.INFO,
    **extra: Any
) -> Generator[Dict[str, Any], None, None]:
    """
    计时上下文管理器

    自动记录操作耗时到日志。

    Args:
        logger: 日志记录器
        operation: 操作名称
        level: 日志级别
        **extra: 额外的日志字段

    Yields:
        包含计时信息的字典（可在 with 块中添加更多数据）

    Example:
        with timed(logger, "登录", account_id="test_user") as ctx:
            await perform_login()
            ctx["status"] = "success"
    """
    context: Dict[str, Any] = {"operation": operation, **extra}
    start_time = time.perf_counter()

    try:
        yield context
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        context["duration_ms"] = round(duration_ms, 2)

        # 构建日志消息
        extra_info = ", ".join(f"{k}={v}" for k, v in extra.items())
        if extra_info:
            message = f"{operation} 完成 [{extra_info}] (耗时: {duration_ms:.0f}ms)"
        else:
            message = f"{operation} 完成 (耗时: {duration_ms:.0f}ms)"

        logger.log(level, message)


class Timer:
    """
    计时器类

    支持手动控制开始/停止的计时器。

    Example:
        timer = Timer()
        timer.start()
        # ... do something ...
        timer.stop()
        print(f"耗时: {timer.duration_ms:.0f}ms")
    """

    def __init__(self):
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None

    def start(self) -> "Timer":
        """开始计时"""
        self._start_time = time.perf_counter()
        self._end_time = None
        return self

    def stop(self) -> "Timer":
        """停止计时"""
        if self._start_time is None:
            raise RuntimeError("Timer not started")
        self._end_time = time.perf_counter()
        return self

    @property
    def duration(self) -> float:
        """返回持续时间（秒）"""
        if self._start_time is None:
            return 0.0
        end = self._end_time or time.perf_counter()
        return end - self._start_time

    @property
    def duration_ms(self) -> float:
        """返回持续时间（毫秒）"""
        return self.duration * 1000

    def __enter__(self) -> "Timer":
        return self.start()

    def __exit__(self, *args) -> None:
        self.stop()


class OperationTimer:
    """
    操作计时器（用于收集统计信息）

    Example:
        timer = OperationTimer()
        with timer.measure("login"):
            await login()
        with timer.measure("captcha"):
            await solve_captcha()

        print(timer.summary())
        # 输出: login: 1234.5ms, captcha: 5678.9ms, total: 6913.4ms
    """

    def __init__(self):
        self._operations: Dict[str, float] = {}
        self._current_op: Optional[str] = None
        self._current_start: Optional[float] = None

    @contextmanager
    def measure(self, operation: str) -> Generator[None, None, None]:
        """
        测量操作耗时

        Args:
            operation: 操作名称
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = (time.perf_counter() - start) * 1000
            self._operations[operation] = duration

    def get(self, operation: str) -> Optional[float]:
        """获取操作耗时（毫秒）"""
        return self._operations.get(operation)

    @property
    def total_ms(self) -> float:
        """总耗时（毫秒）"""
        return sum(self._operations.values())

    def summary(self) -> str:
        """生成摘要字符串"""
        parts = [f"{op}: {duration:.0f}ms" for op, duration in self._operations.items()]
        parts.append(f"total: {self.total_ms:.0f}ms")
        return ", ".join(parts)

    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        return {**self._operations, "total": self.total_ms}


def measure_time(func: Callable) -> Callable:
    """
    装饰器：测量函数执行时间

    Example:
        @measure_time
        def slow_function():
            time.sleep(1)

        slow_function()
        # 输出: slow_function completed in 1000.00ms
    """
    import functools
    import asyncio

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            print(f"{func.__name__} completed in {duration_ms:.2f}ms")

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            print(f"{func.__name__} completed in {duration_ms:.2f}ms")

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


__all__ = [
    "timed",
    "Timer",
    "OperationTimer",
    "measure_time",
]
