"""
认证模块 - Twitter 登录与 2FA 处理

功能:
- Twitter 登录流程
- TOTP 2FA 验证码自动输入
- Cloudflare Turnstile 验证处理

依赖模块:
- cloudflare.py: Cloudflare 检测与处理
- unusual_activity.py: 异常活动验证
- login_flow.py: 登录流程辅助方法
"""

import asyncio
from enum import Enum
from typing import Optional, TYPE_CHECKING

import pyotp

from ..core.browser import BrowserManager
from ..utils.logger import get_logger
from .cloudflare import CloudflareHandler
from .unusual_activity import UnusualActivityHandler
from .login_flow import LoginFlowHelper, human_delay

# 延迟导入避免循环依赖
if TYPE_CHECKING:
    from ..captcha.solver import CaptchaSolver

logger = get_logger(__name__)


class LoginResult(Enum):
    """登录结果"""
    SUCCESS = "success"
    NEED_2FA = "need_2fa"
    NEED_CAPTCHA = "need_captcha"
    NEED_UNLOCK = "need_unlock"
    FAILED = "failed"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_SUSPENDED = "account_suspended"


class TwitterAuth:
    """Twitter 认证处理器"""

    # X (Twitter) 页面 URL
    LOGIN_URL = "https://x.com/i/flow/login"
    HOME_URL = "https://x.com/home"
    UNLOCK_URL = "https://x.com/account/access"

    # 选择器
    SELECTORS = {
        # 登录页面
        "username_input": 'input[autocomplete="username"], input[name="text"][autocomplete="username"]',
        "next_button": 'button[role="button"]:has-text("Next"), button[role="button"]:has-text("下一步"), button:has-text("Next")',
        "password_input": 'input[name="password"], input[type="password"], input[autocomplete="current-password"]',
        "login_button": 'button[data-testid="LoginForm_Login_Button"], button:has-text("Log in"), button:has-text("登录")',

        # 2FA
        "2fa_input": 'input[data-testid="ocfEnterTextTextInput"], input[name="text"]',
        "2fa_next": 'button[data-testid="ocfEnterTextNextButton"], button:has-text("Next"), button:has-text("下一步")',

        # 状态检测
        "home_indicator": '[data-testid="primaryColumn"]',
        "error_message": '[data-testid="error-detail"]',
        "captcha_frame": 'iframe[src*="arkoselabs"], iframe[src*="turnstile"]',
        "unlock_required": 'a[href*="/account/access"], :text("verify")',

        # 登录页面就绪检测
        "login_page_ready": 'input[autocomplete="username"], h1:has-text("Sign in"), h1:has-text("登录")',
    }

    def __init__(
        self,
        browser: BrowserManager,
        username: str,
        password: str,
        totp_secret: Optional[str] = None,
        email: Optional[str] = None,
        solver: Optional["CaptchaSolver"] = None
    ):
        """
        初始化认证处理器

        Args:
            browser: 浏览器管理器
            username: 用户名/邮箱/手机号
            password: 密码
            totp_secret: TOTP 密钥（可选）
            email: 关联邮箱（用于异常活动验证，可选）
            solver: 验证码求解器（用于处理 Cloudflare Turnstile，可选）
        """
        self.browser = browser
        self.username = username
        self.password = password
        self.totp_secret = totp_secret
        self.email = email
        self.solver = solver
        self._logger = get_logger(__name__, account_id=username)

        # 组合辅助模块
        self._cloudflare = CloudflareHandler(browser, solver, username)
        self._unusual_activity = UnusualActivityHandler(browser, username, email, username)
        self._flow_helper = LoginFlowHelper(browser, username)

    def _generate_2fa_code(self) -> Optional[str]:
        """生成 TOTP 验证码"""
        if not self.totp_secret:
            return None
        try:
            totp = pyotp.TOTP(self.totp_secret)
            code = totp.now()
            self._logger.debug(f"生成 2FA 验证码: {code}")
            return code
        except Exception as e:
            self._logger.error(f"生成 2FA 验证码失败: {e}")
            return None

    async def _check_page_state(self) -> LoginResult:
        """检查当前页面状态"""
        page = self.browser.page

        # 检查是否到达首页
        try:
            home = await page.query_selector(self.SELECTORS["home_indicator"])
            if home:
                return LoginResult.SUCCESS
        except:
            pass

        # 检查是否需要验证码
        try:
            captcha = await page.query_selector(self.SELECTORS["captcha_frame"])
            if captcha:
                return LoginResult.NEED_CAPTCHA
        except:
            pass

        # 检查是否需要解锁
        current_url = page.url
        if "/account/access" in current_url or "verify" in current_url.lower():
            return LoginResult.NEED_UNLOCK

        # 检查是否需要 2FA
        try:
            twofa = await page.query_selector(self.SELECTORS["2fa_input"])
            if twofa:
                return LoginResult.NEED_2FA
        except:
            pass

        # 检查账号状态
        try:
            content = await page.content()
            if "suspended" in content.lower():
                return LoginResult.ACCOUNT_SUSPENDED
            if "locked" in content.lower():
                return LoginResult.ACCOUNT_LOCKED
        except:
            pass

        return LoginResult.FAILED

    async def login(self) -> LoginResult:
        """
        执行登录流程

        Returns:
            登录结果
        """
        self._logger.info("开始登录流程")

        # 浏览器预热 - 建立信任
        await self._flow_helper.warm_up_browser(self._cloudflare)

        max_page_retries = 3

        for page_attempt in range(max_page_retries):
            try:
                # 导航到登录页
                self._logger.info("正在导航到登录页...")
                await self.browser.page.goto(
                    self.LOGIN_URL,
                    wait_until="networkidle",
                    timeout=60000
                )

                # 等待页面完全就绪
                await self._flow_helper.wait_for_page_ready()
                await human_delay(1, 2)

                # 检测 Cloudflare 阻塞
                if await self._cloudflare.check_cloudflare_block():
                    self._logger.warning("检测到 Cloudflare 阻塞，尝试处理...")
                    if not await self._cloudflare.handle_cloudflare_block():
                        self._logger.error("Cloudflare 阻塞处理失败")
                        if page_attempt < max_page_retries - 1:
                            self._logger.info("刷新页面重试...")
                            await self.browser.page.reload()
                            await human_delay(2, 3)
                            continue
                        return LoginResult.FAILED

                # 检测并处理 Cloudflare Turnstile
                if not await self._cloudflare.check_and_solve_turnstile():
                    self._logger.error("Cloudflare Turnstile 验证失败")
                    if page_attempt < max_page_retries - 1:
                        await human_delay(2, 3)
                        continue
                    return LoginResult.FAILED

                # 等待登录页面元素出现
                self._logger.info("等待登录表单加载...")
                try:
                    await self.browser.page.wait_for_selector(
                        self.SELECTORS["login_page_ready"],
                        timeout=20000,
                        state="visible"
                    )
                    self._logger.info("登录表单已加载")
                except Exception as e:
                    self._logger.warning(f"登录表单加载超时: {e}")
                    self._save_debug_screenshot(f"login_page_timeout_{page_attempt}")
                    if page_attempt < max_page_retries - 1:
                        await human_delay(2, 3)
                        continue
                    return LoginResult.FAILED

                # 检查是否出现错误页面
                if await self._flow_helper.check_for_error_page():
                    self._logger.warning(f"登录页面加载错误 (尝试 {page_attempt + 1}/{max_page_retries})")
                    if page_attempt < max_page_retries - 1:
                        await self._flow_helper.handle_error_page()
                        continue
                    else:
                        self._logger.error("登录页面持续出现错误，放弃尝试")
                        return LoginResult.FAILED

                # 输入用户名
                self._logger.debug("输入用户名")
                await human_delay(0.5, 1.5)
                if not await self._flow_helper.wait_and_type(
                    self.SELECTORS["username_input"],
                    self.username
                ):
                    self._logger.error("无法找到用户名输入框")
                    if page_attempt < max_page_retries - 1:
                        continue
                    return LoginResult.FAILED

                # 点击下一步
                await human_delay(0.3, 0.8)
                await self._flow_helper.wait_and_click(self.SELECTORS["next_button"])
                await human_delay(1.5, 2.5)

                # 尝试查找密码输入框
                password_found = await self._wait_for_password_input()

                if not password_found:
                    # 检查是否出现了额外的验证步骤
                    self._logger.info("未找到密码输入框，检查是否需要额外验证...")
                    await self._prepare_for_unusual_check()

                    if await self._unusual_activity.handle_unusual_activity():
                        self._logger.info("额外验证步骤已处理，继续登录流程...")
                    else:
                        self._logger.error("处理异常活动验证失败")
                        if page_attempt < max_page_retries - 1:
                            continue
                        return LoginResult.FAILED

                # 输入密码
                self._logger.debug("输入密码")
                await human_delay(0.3, 0.8)
                if not await self._flow_helper.wait_and_type(
                    self.SELECTORS["password_input"],
                    self.password
                ):
                    self._logger.error("无法找到密码输入框")
                    return LoginResult.FAILED

                # 点击登录
                await human_delay(0.3, 0.8)
                await self._flow_helper.wait_and_click(self.SELECTORS["login_button"])
                await human_delay(2, 4)

                # 检查状态
                result = await self._check_page_state()

                # 如果需要 2FA
                if result == LoginResult.NEED_2FA:
                    self._logger.info("需要 2FA 验证")
                    result = await self._handle_2fa()

                self._logger.info(f"登录结果: {result.value}")
                return result

            except Exception as e:
                self._logger.error(f"登录过程出错: {e}")
                if page_attempt < max_page_retries - 1:
                    self._logger.info(f"等待后重试... ({page_attempt + 1}/{max_page_retries})")
                    await human_delay(3, 5)
                    continue
                return LoginResult.FAILED

        return LoginResult.FAILED

    async def _wait_for_password_input(self) -> bool:
        """等待密码输入框出现"""
        try:
            await self.browser.page.wait_for_selector(
                self.SELECTORS["password_input"],
                timeout=5000,
                state="visible"
            )
            return True
        except:
            return False

    async def _prepare_for_unusual_check(self) -> None:
        """准备异常活动检查（等待页面稳定并截图）"""
        try:
            await self.browser.page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass
        await asyncio.sleep(1)
        self._save_debug_screenshot("before_unusual_check")

    def _save_debug_screenshot(self, name: str) -> None:
        """保存调试截图（同步包装）"""
        asyncio.create_task(self._save_debug_screenshot_async(name))

    async def _save_debug_screenshot_async(self, name: str) -> None:
        """保存调试截图"""
        try:
            from pathlib import Path
            output_dir = Path("output/debug")
            output_dir.mkdir(parents=True, exist_ok=True)
            await self.browser.page.screenshot(
                path=str(output_dir / f"{name}_{self.username}.png")
            )
            self._logger.debug(f"已保存调试截图: {name}")
        except:
            pass

    async def _handle_2fa(self) -> LoginResult:
        """处理 2FA 验证"""
        if not self.totp_secret:
            self._logger.warning("需要 2FA 但未提供 TOTP 密钥")
            return LoginResult.NEED_2FA

        code = self._generate_2fa_code()
        if not code:
            return LoginResult.FAILED

        self._logger.info("输入 2FA 验证码...")

        # 输入验证码
        if not await self._flow_helper.wait_and_type(self.SELECTORS["2fa_input"], code):
            self._logger.error("无法输入 2FA 验证码")
            return LoginResult.FAILED

        # 点击确认
        await human_delay(0.3, 0.8)
        await self._flow_helper.wait_and_click(self.SELECTORS["2fa_next"])

        # 等待页面导航完成
        self._logger.info("等待 2FA 验证完成...")
        await human_delay(3, 5)

        # 等待网络空闲
        try:
            await self.browser.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            self._logger.debug(f"等待网络空闲超时: {e}")

        # 额外等待确保页面渲染完成
        await human_delay(2, 3)

        # 多次尝试检测首页
        for attempt in range(3):
            result = await self._check_page_state()
            if result == LoginResult.SUCCESS:
                return result
            if result != LoginResult.FAILED:
                return result
            self._logger.debug(f"状态检测尝试 {attempt + 1}/3，继续等待...")
            await human_delay(1, 2)

        # 最后检查 URL 是否已到达首页
        current_url = self.browser.page.url
        if "/home" in current_url:
            self._logger.info("通过 URL 确认登录成功")
            return LoginResult.SUCCESS

        self._logger.warning(f"2FA 后状态检测失败，当前 URL: {current_url}")
        return await self._check_page_state()


async def perform_login(
    browser: BrowserManager,
    username: str,
    password: str,
    totp_secret: Optional[str] = None,
    email: Optional[str] = None,
    solver: Optional["CaptchaSolver"] = None
) -> LoginResult:
    """
    执行登录（便捷函数）

    Args:
        browser: 浏览器管理器
        username: 用户名
        password: 密码
        totp_secret: TOTP 密钥（可选）
        email: 关联邮箱（用于异常活动验证，可选）
        solver: 验证码求解器（用于处理 Cloudflare Turnstile，可选）

    Returns:
        登录结果
    """
    auth = TwitterAuth(browser, username, password, totp_secret, email, solver)
    return await auth.login()
