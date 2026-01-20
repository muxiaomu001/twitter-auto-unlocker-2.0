"""
配置模型模块 (2.0 版本)

功能:
- 使用 dataclass 集中管理配置
- 支持 YAML 文件加载
- 支持 CLI 参数合并
- 类型校验与默认值

版本: 2.0 - 支持 BitBrowser + 插件验证码配置
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

import yaml

from .errors import ConfigError, MissingConfigError, InvalidConfigError


@dataclass
class CaptchaConfig:
    """
    验证码配置（2.0 简化版）

    支持两种模式:
    - plugin: 使用浏览器插件处理验证码（支持 2captcha/YesCaptcha）
    - api: 使用 YesCaptcha 图像识别 API
    """
    mode: str = "plugin"  # "plugin" 或 "api"
    api_key: str = ""
    timeout: int = 30
    max_retries: int = 3
    max_rounds: int = 10  # 单次验证最大轮数

    # 插件模式配置
    plugin_auto_wait: bool = True
    plugin_max_wait_time: int = 120  # 秒
    plugin_provider: str = "auto"  # auto | 2captcha | yescaptcha
    plugin_twocaptcha_key: str = ""
    plugin_twocaptcha_ext_id: str = ""
    plugin_twocaptcha_turnstile_only: bool = True
    plugin_yescaptcha_key: str = ""
    plugin_yescaptcha_ext_id: str = ""
    plugin_yescaptcha_funcaptcha_only: bool = True

    def validate(self) -> None:
        """校验配置"""
        if self.mode == "api" and not self.api_key:
            raise MissingConfigError("captcha.api_key 是必需的配置项")

        if self.mode not in ("plugin", "api"):
            raise InvalidConfigError(
                f"captcha.mode 无效: {self.mode}，有效值: plugin, api"
            )

        if self.timeout < 10:
            raise InvalidConfigError("captcha.timeout 不能小于 10 秒")
        if self.timeout > 300:
            raise InvalidConfigError("captcha.timeout 不能大于 300 秒")

    def is_plugin_mode(self) -> bool:
        """是否使用插件模式"""
        return self.mode.lower() == "plugin"

    def plugin_provider_order(self) -> list:
        """获取插件优先级"""
        provider = (self.plugin_provider or "auto").strip().lower()
        if provider in ("2captcha", "twocaptcha", "2cap"):
            return ["2captcha"]
        if provider in ("yescaptcha", "yc"):
            return ["yescaptcha"]
        return ["2captcha", "yescaptcha"]

    def get_twocaptcha_key(self) -> str:
        """获取 2captcha 插件 Key"""
        return self.plugin_twocaptcha_key or ""

    def get_yescaptcha_key(self) -> str:
        """获取 YesCaptcha 插件 Key（优先 plugin 配置）"""
        return self.plugin_yescaptcha_key or self.api_key


@dataclass
class BrowserConfig:
    """浏览器配置（BitBrowser）"""
    api_url: str = "http://127.0.0.1:54345"
    page_timeout: int = 60  # 秒
    save_screenshots: bool = True
    screenshot_dir: str = "screenshots"

    @property
    def timeout_ms(self) -> int:
        """返回毫秒级超时"""
        return self.page_timeout * 1000

    def validate(self) -> None:
        """校验配置"""
        if self.page_timeout < 10:
            raise InvalidConfigError("browser.page_timeout 不能小于 10 秒")
        if self.page_timeout > 300:
            raise InvalidConfigError("browser.page_timeout 不能大于 300 秒")


@dataclass
class ConcurrencyConfig:
    """并发配置"""
    max_browsers: int = 5
    task_delay: int = 2  # 任务间隔（秒）

    def validate(self) -> None:
        """校验配置"""
        if self.max_browsers < 1:
            raise InvalidConfigError("concurrency.max_browsers 不能小于 1")
        if self.max_browsers > 20:
            raise InvalidConfigError("concurrency.max_browsers 不能大于 20")


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    delay_base: int = 5
    delay_increment: int = 5

    def validate(self) -> None:
        """校验配置"""
        if self.max_attempts < 1:
            raise InvalidConfigError("retry.max_attempts 不能小于 1")
        if self.max_attempts > 10:
            raise InvalidConfigError("retry.max_attempts 不能大于 10")


@dataclass
class OutputConfig:
    """输出配置"""
    dir: Path = field(default_factory=lambda: Path("./output"))
    export_cookies: bool = True
    success_file: str = "success.txt"
    failed_file: str = "failed.txt"

    def __post_init__(self):
        """确保 dir 是 Path 对象"""
        if isinstance(self.dir, str):
            self.dir = Path(self.dir)

    def validate(self) -> None:
        """校验配置"""
        # 尝试创建目录（如果不存在）
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise InvalidConfigError(f"无法创建输出目录 {self.dir}: {e}")


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file_output: bool = True
    file_name: str = "unlock.log"

    def validate(self) -> None:
        """校验配置"""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level.upper() not in valid_levels:
            raise InvalidConfigError(
                f"logging.level 无效: {self.level}，有效值: {valid_levels}"
            )


@dataclass
class TwitterConfig:
    """Twitter 相关配置"""
    unlock_url: str = "https://x.com/account/access"
    login_url: str = "https://x.com/i/flow/login"
    home_url: str = "https://x.com/home"


@dataclass
class AppConfig:
    """应用配置（顶级）"""
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    twitter: TwitterConfig = field(default_factory=TwitterConfig)
    debug: bool = False

    def validate(self) -> None:
        """校验所有配置"""
        self.captcha.validate()
        self.browser.validate()
        self.concurrency.validate()
        self.retry.validate()
        self.output.validate()
        self.logging.validate()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """
        从字典创建配置

        Args:
            data: 配置字典

        Returns:
            AppConfig 实例
        """
        captcha_data = data.get("captcha", {})
        browser_data = data.get("browser", {})
        concurrency_data = data.get("concurrency", {})
        retry_data = data.get("retry", {})
        output_data = data.get("output", {})
        logging_data = data.get("logging", {})
        twitter_data = data.get("twitter", {})

        # 解析插件配置
        plugin_data = captcha_data.get("plugin", {})
        twocaptcha_data = plugin_data.get("twocaptcha", {})
        yescaptcha_data = plugin_data.get("yescaptcha", {})
        api_data = captcha_data.get("api", {})

        return cls(
            captcha=CaptchaConfig(
                mode=captcha_data.get("mode", "plugin"),
                api_key=captcha_data.get("api_key", ""),
                timeout=api_data.get("timeout", 30),
                max_retries=api_data.get("max_retries", 3),
                max_rounds=api_data.get("max_rounds", 10),
                plugin_auto_wait=plugin_data.get("auto_wait", True),
                plugin_max_wait_time=plugin_data.get("max_wait_time", 120),
                plugin_provider=plugin_data.get("provider", "auto"),
                plugin_twocaptcha_key=twocaptcha_data.get("api_key", ""),
                plugin_twocaptcha_ext_id=twocaptcha_data.get("ext_id", ""),
                plugin_twocaptcha_turnstile_only=twocaptcha_data.get(
                    "turnstile_only", True
                ),
                plugin_yescaptcha_key=yescaptcha_data.get("api_key", ""),
                plugin_yescaptcha_ext_id=yescaptcha_data.get("ext_id", ""),
                plugin_yescaptcha_funcaptcha_only=yescaptcha_data.get(
                    "funcaptcha_only", True
                ),
            ),
            browser=BrowserConfig(
                api_url=browser_data.get("api_url", "http://127.0.0.1:54345"),
                page_timeout=browser_data.get("page_timeout", 60),
                save_screenshots=browser_data.get("save_screenshots", True),
                screenshot_dir=browser_data.get("screenshot_dir", "screenshots"),
            ),
            concurrency=ConcurrencyConfig(
                max_browsers=concurrency_data.get("max_browsers", 5),
                task_delay=concurrency_data.get("task_delay", 2),
            ),
            retry=RetryConfig(
                max_attempts=retry_data.get("max_attempts", 3),
                delay_base=retry_data.get("delay_base", 5),
                delay_increment=retry_data.get("delay_increment", 5),
            ),
            output=OutputConfig(
                dir=Path(output_data.get("dir", "./output")),
                export_cookies=output_data.get("export_cookies", True),
                success_file=output_data.get("success_file", "success.txt"),
                failed_file=output_data.get("failed_file", "failed.txt"),
            ),
            logging=LoggingConfig(
                level=logging_data.get("level", "INFO"),
                file_output=logging_data.get("file_output", True),
                file_name=logging_data.get("file_name", "unlock.log"),
            ),
            twitter=TwitterConfig(
                unlock_url=twitter_data.get("unlock_url", "https://x.com/account/access"),
                login_url=twitter_data.get("login_url", "https://x.com/i/flow/login"),
                home_url=twitter_data.get("home_url", "https://x.com/home"),
            ),
            debug=data.get("debug", False),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        """
        从 YAML 文件加载配置

        Args:
            path: YAML 文件路径

        Returns:
            AppConfig 实例

        Raises:
            ConfigError: 加载失败
        """
        if not path.exists():
            raise ConfigError(f"配置文件不存在: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML 解析错误: {e}")
        except Exception as e:
            raise ConfigError(f"加载配置文件失败: {e}")

        return cls.from_dict(data)

    @classmethod
    def merge_cli_args(
        cls,
        config: "AppConfig",
        *,
        api_key: Optional[str] = None,
        output_dir: Optional[Path] = None,
        concurrency: Optional[int] = None,
        max_attempts: Optional[int] = None,
        debug: bool = False,
    ) -> "AppConfig":
        """
        合并 CLI 参数到配置

        CLI 参数优先级高于配置文件。

        Args:
            config: 基础配置
            api_key: YesCaptcha API Key
            output_dir: 输出目录
            concurrency: 并发数
            max_attempts: 最大重试次数
            debug: 调试模式

        Returns:
            合并后的配置
        """
        # 创建新配置（深拷贝）
        merged = cls.from_dict({
            "captcha": {
                "mode": config.captcha.mode,
                "api_key": api_key or config.captcha.api_key,
                "api": {
                    "timeout": config.captcha.timeout,
                    "max_retries": config.captcha.max_retries,
                    "max_rounds": config.captcha.max_rounds,
                },
                "plugin": {
                    "auto_wait": config.captcha.plugin_auto_wait,
                    "max_wait_time": config.captcha.plugin_max_wait_time,
                    "provider": config.captcha.plugin_provider,
                    "twocaptcha": {
                        "api_key": config.captcha.plugin_twocaptcha_key,
                        "ext_id": config.captcha.plugin_twocaptcha_ext_id,
                        "turnstile_only": config.captcha.plugin_twocaptcha_turnstile_only,
                    },
                    "yescaptcha": {
                        "api_key": config.captcha.plugin_yescaptcha_key,
                        "ext_id": config.captcha.plugin_yescaptcha_ext_id,
                        "funcaptcha_only": config.captcha.plugin_yescaptcha_funcaptcha_only,
                    },
                },
            },
            "browser": {
                "api_url": config.browser.api_url,
                "page_timeout": config.browser.page_timeout,
                "save_screenshots": config.browser.save_screenshots,
                "screenshot_dir": config.browser.screenshot_dir,
            },
            "concurrency": {
                "max_browsers": concurrency or config.concurrency.max_browsers,
                "task_delay": config.concurrency.task_delay,
            },
            "retry": {
                "max_attempts": max_attempts or config.retry.max_attempts,
                "delay_base": config.retry.delay_base,
                "delay_increment": config.retry.delay_increment,
            },
            "output": {
                "dir": str(output_dir or config.output.dir),
                "export_cookies": config.output.export_cookies,
                "success_file": config.output.success_file,
                "failed_file": config.output.failed_file,
            },
            "logging": {
                "level": "DEBUG" if debug else config.logging.level,
                "file_output": config.logging.file_output,
                "file_name": config.logging.file_name,
            },
            "twitter": {
                "unlock_url": config.twitter.unlock_url,
                "login_url": config.twitter.login_url,
                "home_url": config.twitter.home_url,
            },
            "debug": debug or config.debug,
        })

        return merged

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            配置字典
        """
        return {
            "captcha": {
                "mode": self.captcha.mode,
                "api_key": self.captcha.api_key,
                "api": {
                    "timeout": self.captcha.timeout,
                    "max_retries": self.captcha.max_retries,
                    "max_rounds": self.captcha.max_rounds,
                },
                "plugin": {
                    "auto_wait": self.captcha.plugin_auto_wait,
                    "max_wait_time": self.captcha.plugin_max_wait_time,
                    "provider": self.captcha.plugin_provider,
                    "twocaptcha": {
                        "api_key": self.captcha.plugin_twocaptcha_key,
                        "ext_id": self.captcha.plugin_twocaptcha_ext_id,
                        "turnstile_only": self.captcha.plugin_twocaptcha_turnstile_only,
                    },
                    "yescaptcha": {
                        "api_key": self.captcha.plugin_yescaptcha_key,
                        "ext_id": self.captcha.plugin_yescaptcha_ext_id,
                        "funcaptcha_only": self.captcha.plugin_yescaptcha_funcaptcha_only,
                    },
                },
            },
            "browser": {
                "api_url": self.browser.api_url,
                "page_timeout": self.browser.page_timeout,
                "save_screenshots": self.browser.save_screenshots,
                "screenshot_dir": self.browser.screenshot_dir,
            },
            "concurrency": {
                "max_browsers": self.concurrency.max_browsers,
                "task_delay": self.concurrency.task_delay,
            },
            "retry": {
                "max_attempts": self.retry.max_attempts,
                "delay_base": self.retry.delay_base,
                "delay_increment": self.retry.delay_increment,
            },
            "output": {
                "dir": str(self.output.dir),
                "export_cookies": self.output.export_cookies,
                "success_file": self.output.success_file,
                "failed_file": self.output.failed_file,
            },
            "logging": {
                "level": self.logging.level,
                "file_output": self.logging.file_output,
                "file_name": self.logging.file_name,
            },
            "twitter": {
                "unlock_url": self.twitter.unlock_url,
                "login_url": self.twitter.login_url,
                "home_url": self.twitter.home_url,
            },
            "debug": self.debug,
        }


def load_config(
    config_path: Optional[Path] = None,
    **cli_overrides
) -> AppConfig:
    """
    加载配置（便捷函数）

    Args:
        config_path: 配置文件路径（可选）
        **cli_overrides: CLI 参数覆盖

    Returns:
        AppConfig 实例
    """
    # 加载基础配置
    if config_path and config_path.exists():
        config = AppConfig.from_yaml(config_path)
    else:
        config = AppConfig()

    # 合并 CLI 参数
    if cli_overrides:
        config = AppConfig.merge_cli_args(config, **cli_overrides)

    return config


__all__ = [
    "CaptchaConfig",
    "BrowserConfig",
    "ConcurrencyConfig",
    "RetryConfig",
    "OutputConfig",
    "LoggingConfig",
    "TwitterConfig",
    "AppConfig",
    "load_config",
]
