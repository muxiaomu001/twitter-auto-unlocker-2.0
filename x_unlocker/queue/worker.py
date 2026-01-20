"""
并发任务管理模块 (2.0 版本)

功能:
- 使用 asyncio.Semaphore 控制并发数
- 任务状态跟踪
- 批量处理账号
- 仅支持 BitBrowser

版本: 2.0 - 仅支持 BitBrowser + 插件验证码
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from ..account.parser import AccountInfo
from ..captcha.factory import create_solver, CaptchaConfig, is_plugin_mode
from ..captcha.plugin_config import apply_captcha_plugin_config
from ..core.browser_factory import create_browser_provider
from ..core.config import AppConfig
from ..core.errors import XUnlockerError, is_retryable, get_error_category, ErrorCategory
from ..core.session import SessionManager
from ..core.unlock_flow import UnlockResult, unlock_account
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class TaskResult:
    """任务结果"""
    account_id: str
    status: TaskStatus
    message: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    unlock_result: Optional[UnlockResult] = None
    error_category: Optional[ErrorCategory] = None
    retryable: bool = False

    @property
    def duration(self) -> Optional[float]:
        """任务耗时（秒）"""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


@dataclass
class WorkerStats:
    """工作统计"""
    total: int = 0
    pending: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    retryable_errors: int = 0
    fatal_errors: int = 0
    error_categories: dict = field(default_factory=dict)
    results: List[TaskResult] = field(default_factory=list)

    def update(self, result: TaskResult) -> None:
        """更新统计"""
        self.results.append(result)
        if result.status == TaskStatus.SUCCESS:
            self.success += 1
        else:
            self.failed += 1
            if result.error_category:
                cat_name = result.error_category.value
                self.error_categories[cat_name] = self.error_categories.get(cat_name, 0) + 1
            if result.retryable:
                self.retryable_errors += 1
            else:
                self.fatal_errors += 1
        self.running -= 1

    def summary(self) -> str:
        """生成摘要"""
        if self.total == 0:
            return "无任务"

        base = (
            f"总计: {self.total}, "
            f"成功: {self.success}, "
            f"失败: {self.failed}, "
            f"成功率: {self.success / self.total * 100:.1f}%"
        )

        if self.failed > 0:
            base += f" (可重试: {self.retryable_errors}, 致命: {self.fatal_errors})"

        return base


class UnlockWorker:
    """解锁工作器 (2.0 版本)"""

    def __init__(
        self,
        accounts: List[AccountInfo],
        config: AppConfig,
        on_task_complete: Optional[Callable[[TaskResult], None]] = None,
    ):
        """
        初始化工作器

        Args:
            accounts: 账号列表
            config: 应用配置
            on_task_complete: 任务完成回调
        """
        self.accounts = accounts
        self.config = config
        self.on_task_complete = on_task_complete

        self._semaphore = asyncio.Semaphore(config.concurrency.max_browsers)
        self._stats = WorkerStats(total=len(accounts), pending=len(accounts))
        self._running = False
        self._solver = None

    @property
    def stats(self) -> WorkerStats:
        """获取统计信息"""
        return self._stats

    async def _process_account(
        self,
        account: AccountInfo,
    ) -> TaskResult:
        """
        处理单个账号

        Args:
            account: 账号信息

        Returns:
            任务结果
        """
        result = TaskResult(
            account_id=account.username,
            status=TaskStatus.RUNNING,
            started_at=datetime.now()
        )

        self._stats.pending -= 1
        self._stats.running += 1

        logger.info(f"开始处理账号: {account.username}")

        try:
            # 使用工厂函数创建 BitBrowser 实例
            async with create_browser_provider(
                bitbrowser_api=self.config.browser.api_url,
                proxy=account.proxy,
                browser_name=f"unlock_{account.username}",
                page_timeout=self.config.browser.timeout_ms,
            ) as browser:
                await apply_captcha_plugin_config(browser, self.config)
                session_manager = SessionManager(self.config.output.dir)

                unlock_result = await unlock_account(
                    browser=browser,
                    solver=self._solver,
                    session_manager=session_manager,
                    account=account,
                    config=self.config,
                )

                result.unlock_result = unlock_result
                result.status = TaskStatus.SUCCESS if unlock_result.success else TaskStatus.FAILED
                result.message = unlock_result.message

        except Exception as e:
            logger.error(f"处理账号 {account.username} 异常: {e}")
            result.status = TaskStatus.FAILED
            result.message = str(e)
            result.error_category = get_error_category(e)
            result.retryable = is_retryable(e)

        result.finished_at = datetime.now()

        # 更新统计
        self._stats.update(result)

        # 调用回调
        if self.on_task_complete:
            try:
                self.on_task_complete(result)
            except Exception as e:
                logger.warning(f"任务完成回调异常: {e}")

        status_text = "成功" if result.status == TaskStatus.SUCCESS else "失败"
        duration = result.duration or 0
        logger.info(
            f"账号 {account.username} 处理{status_text}，"
            f"耗时 {duration:.1f}s，{result.message}"
        )

        return result

    async def _worker(
        self,
        account: AccountInfo,
    ) -> TaskResult:
        """
        带并发控制的工作协程

        Args:
            account: 账号信息

        Returns:
            任务结果
        """
        async with self._semaphore:
            # 任务间延迟
            if self.config.concurrency.task_delay > 0:
                await asyncio.sleep(self.config.concurrency.task_delay)
            return await self._process_account(account)

    async def run(self) -> WorkerStats:
        """
        运行批量处理

        Returns:
            工作统计
        """
        if self._running:
            raise RuntimeError("工作器已在运行中")

        self._running = True
        start_time = datetime.now()

        captcha_mode = self.config.captcha.mode
        if self.config.captcha.is_plugin_mode():
            providers = "+".join(self.config.captcha.plugin_provider_order())
            captcha_label = f"插件({providers})"
        else:
            captcha_label = "YesCaptcha(API)"
        logger.info(
            f"开始批量处理: {len(self.accounts)} 个账号, "
            f"并发数: {self.config.concurrency.max_browsers}, "
            f"浏览器: BitBrowser, "
            f"验证码: {captcha_label} ({captcha_mode} 模式)"
        )

        try:
            # 创建验证码求解器（API 模式）
            # 插件模式下也创建，用于备用
            captcha_config = CaptchaConfig(
                mode=self.config.captcha.mode,
                api_key=self.config.captcha.api_key,
                timeout=self.config.captcha.timeout,
                max_retries=self.config.captcha.max_retries,
                max_rounds=self.config.captcha.max_rounds,
            )

            if not is_plugin_mode(captcha_config):
                # API 模式：创建求解器
                self._solver = create_solver(captcha_config)
                logger.info("已创建 YesCaptcha 图像识别求解器")
            else:
                # 插件模式：不需要求解器（插件自动处理）
                self._solver = None
                logger.info("使用插件模式，请确保浏览器已安装对应人机助手")

            # 创建所有任务
            tasks = [
                self._worker(account)
                for account in self.accounts
            ]

            # 并发执行
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"批量处理异常: {e}")

        finally:
            self._running = False

        # 计算总耗时
        total_time = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"批量处理完成: {self._stats.summary()}, "
            f"总耗时: {total_time:.1f}s"
        )

        return self._stats

    def stop(self) -> None:
        """停止处理（优雅关闭）"""
        logger.info("正在停止工作器...")
        self._running = False


async def run_batch_unlock(
    accounts: List[AccountInfo],
    config: AppConfig,
    on_task_complete: Optional[Callable[[TaskResult], None]] = None,
) -> WorkerStats:
    """
    批量解锁账号（便捷函数）

    Args:
        accounts: 账号列表
        config: 应用配置
        on_task_complete: 任务完成回调

    Returns:
        工作统计
    """
    worker = UnlockWorker(
        accounts=accounts,
        config=config,
        on_task_complete=on_task_complete,
    )

    return await worker.run()


__all__ = [
    "TaskStatus",
    "TaskResult",
    "WorkerStats",
    "UnlockWorker",
    "run_batch_unlock",
]
