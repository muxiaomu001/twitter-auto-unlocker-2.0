"""
日志模块 - 提供结构化日志功能

支持:
- 控制台彩色输出
- JSON 格式日志（可选）
- 文件日志（可选）
- 账号级别日志隔离
- 结构化日志字段
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union


class ColoredFormatter(logging.Formatter):
    """控制台彩色日志格式化器"""

    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        # 保存原始 levelname
        original_levelname = record.levelname
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        result = super().format(record)
        # 恢复原始 levelname
        record.levelname = original_levelname
        return result


class JsonFormatter(logging.Formatter):
    """
    JSON 格式日志格式化器

    输出结构化 JSON 日志，便于日志收集和分析。
    """

    # 标准字段
    STANDARD_FIELDS = {
        "account_id", "flow_state", "attempt", "duration_ms",
        "captcha_type", "task_id", "error_category"
    }

    def format(self, record: logging.LogRecord) -> str:
        # 基础日志结构
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加标准字段（如果存在）
        for field in self.STANDARD_FIELDS:
            if hasattr(record, field) and getattr(record, field) is not None:
                log_data[field] = getattr(record, field)

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加额外字段（从 record.__dict__ 中提取非标准字段）
        extra_fields = {}
        skip_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "taskName", "message"
        }
        for key, value in record.__dict__.items():
            if key not in skip_fields and key not in self.STANDARD_FIELDS:
                if not key.startswith("_"):
                    try:
                        # 确保可 JSON 序列化
                        json.dumps(value)
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)

        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """
    结构化日志适配器

    支持在日志中添加结构化字段。

    Example:
        logger = get_structured_logger(__name__, account_id="test_user")
        logger.info("登录成功", extra={"duration_ms": 1234, "attempt": 2})
    """

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        # 合并额外字段到 extra
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[Path] = None,
    account_id: Optional[str] = None,
    json_format: bool = False
) -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日志文件路径（可选）
        account_id: 账号标识（可选，用于日志前缀）
        json_format: 是否使用 JSON 格式（仅文件日志）

    Returns:
        配置好的日志记录器
    """
    # 如果有账号标识，添加到日志名称
    logger_name = f"{name}:{account_id}" if account_id else name
    logger = logging.getLogger(logger_name)

    # 避免重复配置
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # 日志格式
    if account_id:
        fmt = f"%(asctime)s | %(levelname)s | [{account_id}] %(message)s"
    else:
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # 控制台处理器（彩色）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter(fmt, datefmt=date_fmt))
    logger.addHandler(console_handler)

    # 文件处理器（可选）
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')

        if json_format:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))

        logger.addHandler(file_handler)

    return logger


def get_structured_logger(
    name: str,
    account_id: Optional[str] = None,
    **extra_fields
) -> StructuredLoggerAdapter:
    """
    获取结构化日志记录器

    Args:
        name: 日志记录器名称
        account_id: 账号标识
        **extra_fields: 额外的默认字段

    Returns:
        结构化日志适配器
    """
    base_logger = get_logger(name, account_id=account_id)

    # 构建额外字段
    extra = {**extra_fields}
    if account_id:
        extra["account_id"] = account_id

    return StructuredLoggerAdapter(base_logger, extra)


def get_account_logger(
    account_id: str,
    output_dir: Path,
    level: str = "INFO",
    json_format: bool = False
) -> logging.Logger:
    """
    获取账号专用日志记录器

    Args:
        account_id: 账号标识
        output_dir: 输出目录
        level: 日志级别
        json_format: 是否使用 JSON 格式

    Returns:
        账号专用日志记录器
    """
    log_file = output_dir / account_id / "unlock.log"
    return get_logger(
        name="unlock",
        level=level,
        log_file=log_file,
        account_id=account_id,
        json_format=json_format
    )


# 全局主日志记录器
_main_logger: Optional[logging.Logger] = None
_json_format: bool = False


def setup_main_logger(
    level: str = "INFO",
    json_format: bool = False
) -> logging.Logger:
    """设置并返回主日志记录器"""
    global _main_logger, _json_format
    _json_format = json_format
    _main_logger = get_logger("x_unlocker", level=level)
    return _main_logger


def get_main_logger() -> logging.Logger:
    """获取主日志记录器（如未设置则创建默认）"""
    global _main_logger
    if _main_logger is None:
        _main_logger = setup_main_logger()
    return _main_logger


def setup_file_logging(
    log_file: Path,
    level: str = "INFO",
    json_format: bool = False
) -> None:
    """
    设置全局文件日志

    Args:
        log_file: 日志文件路径
        level: 日志级别
        json_format: 是否使用 JSON 格式
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 添加文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')

    if json_format:
        file_handler.setFormatter(JsonFormatter())
    else:
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        date_fmt = "%Y-%m-%d %H:%M:%S"
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))

    root_logger.addHandler(file_handler)


def setup_json_file_logging(
    log_file: Path,
    level: str = "INFO"
) -> None:
    """
    设置 JSON 格式文件日志

    Args:
        log_file: 日志文件路径
        level: 日志级别
    """
    setup_file_logging(log_file, level, json_format=True)


__all__ = [
    "get_logger",
    "get_structured_logger",
    "get_account_logger",
    "get_main_logger",
    "setup_main_logger",
    "setup_file_logging",
    "setup_json_file_logging",
    "ColoredFormatter",
    "JsonFormatter",
    "StructuredLoggerAdapter",
]
