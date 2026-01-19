"""
Utils 模块 - 工具函数

导出:
- get_logger: 获取日志器
- setup_file_logging: 设置文件日志
- get_account_logger: 获取账号专用日志器
- human_delay: 人类行为模拟延迟
- exponential_backoff: 指数退避计算
- wait_for_backoff: 执行指数退避等待
- safe_screenshot: 安全截图封装
- wait_for_network_idle: 等待网络空闲
- wait_for_page_load: 等待页面加载
"""

from .logger import get_logger, setup_file_logging, get_account_logger
from .helpers import (
    HUMAN_DELAY_MIN,
    HUMAN_DELAY_MAX,
    human_delay,
    exponential_backoff,
    wait_for_backoff,
    safe_screenshot,
    wait_for_network_idle,
    wait_for_page_load,
    retry_with_backoff,
    clamp,
    safe_filename,
)

__all__ = [
    # 日志
    "get_logger",
    "setup_file_logging",
    "get_account_logger",
    # 延迟与重试
    "HUMAN_DELAY_MIN",
    "HUMAN_DELAY_MAX",
    "human_delay",
    "exponential_backoff",
    "wait_for_backoff",
    "retry_with_backoff",
    # 页面操作
    "safe_screenshot",
    "wait_for_network_idle",
    "wait_for_page_load",
    # 工具函数
    "clamp",
    "safe_filename",
]
