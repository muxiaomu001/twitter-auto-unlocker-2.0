"""
解锁流程模块 - 状态机驱动的主流程 (2.0 版本)

功能:
- 状态机管理解锁流程
- 协调登录、验证码处理、结果保存
- 支持 YesCaptcha 插件模式和 API 模式
- 重试机制与错误处理

版本: 2.0 - BitBrowser + YesCaptcha
"""

import asyncio
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

from ..account.auth import TwitterAuth, LoginResult
from ..account.cloudflare import CloudflareHandler

if TYPE_CHECKING:
    from ..captcha.arkose import ArkoseHandler
    from ..captcha.turnstile import TurnstileHandler
from ..account.parser import AccountInfo
from ..captcha.arkose import ArkoseHandler
from ..captcha.turnstile import TurnstileHandler
from ..core.browser import BrowserManager
from ..core.config import AppConfig
from ..core.session import SessionManager
from ..utils.logger import get_logger

logger = get_logger(__name__)


class UnlockState(Enum):
    """解锁状态"""
    INIT = "init"
    LOGGING_IN = "logging_in"
    DETECTING_CAPTCHA = "detecting_captcha"
    SOLVING_TURNSTILE = "solving_turnstile"
    SOLVING_ARKOSE = "solving_arkose"
    WAITING_PLUGIN = "waiting_plugin"  # 等待插件处理
    VERIFYING = "verifying"
    SAVING = "saving"
    SUCCESS = "success"
    FAILED = "failed"


class UnlockResult:
    """解锁结果"""

    def __init__(
        self,
        success: bool,
        account_id: str,
        message: str = "",
        state: UnlockState = UnlockState.INIT,
        attempts: int = 0
    ):
        self.success = success
        self.account_id = account_id
        self.message = message
        self.final_state = state
        self.attempts = attempts

    def __repr__(self):
        status = "成功" if self.success else "失败"
        return f"UnlockResult({self.account_id}: {status}, {self.message})"


class UnlockFlow:
    """解锁流程控制器 (2.0 版本)"""

    # X (Twitter) 解锁页面 URL
    UNLOCK_URL = "https://x.com/account/access"
    HOME_URL = "https://x.com/home"

    # 选择器
    SELECTORS = {
        "unlock_button": 'button[data-testid="ocfStartButton"], button:has-text("Start"), button:has-text("开始")',
        "continue_button": 'button[data-testid="ocfVerifySuccessNextButton"], button:has-text("Continue"), button:has-text("继续")',
        "success_indicator": '[data-testid="primaryColumn"]',
        "error_message": '[data-testid="error-detail"]',
        # 验证码相关选择器
        "captcha_iframe": 'iframe[src*="arkoselabs"], iframe[src*="funcaptcha"], iframe[id*="arkose"]',
        "turnstile_iframe": 'iframe[src*="turnstile"], iframe[src*="cloudflare"]',
        # 锁定页面检测
        "locked_title": 'h1:has-text("Your account has been locked"), h1:has-text("账号已被锁定")',
        "challenge_text": ':text("Pass a challenge"), :text("通过验证")',
    }

    def __init__(
        self,
        browser: BrowserManager,
        solver,  # YesCaptchaSolver 或 None (插件模式)
        session_manager: SessionManager,
        account: AccountInfo,
        config: AppConfig,
    ):
        """
        初始化解锁流程

        Args:
            browser: 浏览器管理器
            solver: YesCaptcha 求解器（API 模式）或 None（插件模式）
            session_manager: 会话管理器
            account: 账号信息
            config: 应用配置
        """
        self.browser = browser
        self.solver = solver
        self.session_manager = session_manager
        self.account = account
        self.config = config

        self._logger = get_logger(__name__, account_id=account.username)
        self._state = UnlockState.INIT
        self._attempts = 0

        # 懒加载 Handler 实例
        self._turnstile_handler: Optional["TurnstileHandler"] = None
        self._arkose_handler: Optional["ArkoseHandler"] = None

    @property
    def state(self) -> UnlockState:
        """当前状态"""
        return self._state

    @property
    def is_plugin_mode(self) -> bool:
        """是否使用插件模式"""
        return self.config.captcha.is_plugin_mode()

    def _get_turnstile_handler(self) -> "TurnstileHandler":
        """懒加载 Turnstile Handler"""
        if self._turnstile_handler is None:
            self._turnstile_handler = TurnstileHandler(
                browser=self.browser,
                solver=self.solver,
                account_id=self.account.username
            )
        return self._turnstile_handler

    def _get_arkose_handler(self) -> "ArkoseHandler":
        """懒加载 Arkose Handler"""
        if self._arkose_handler is None:
            self._arkose_handler = ArkoseHandler(
                browser=self.browser,
                solver=self.solver,
                account_id=self.account.username
            )
        return self._arkose_handler

    def _set_state(self, new_state: UnlockState) -> None:
        """切换状态"""
        self._logger.debug(f"状态切换: {self._state.value} -> {new_state.value}")
        self._state = new_state

    async def _dispatch_click_events(self, selector: str) -> bool:
        """兜底：通过事件链派发点击"""
        page = self.browser.page
        try:
            return await page.evaluate(
                """
                (selector) => {
                    const btn = document.querySelector(selector);
                    if (!btn) return false;
                    const rect = btn.getBoundingClientRect();
                    const x = rect.left + rect.width * 0.5;
                    const y = rect.top + rect.height * 0.6;

                    const eventTypes = [
                        "pointerover", "pointerenter",
                        "mouseover", "mouseenter",
                        "pointermove", "mousemove",
                        "pointerdown", "mousedown",
                        "focus",
                        "pointerup", "mouseup",
                        "click"
                    ];

                    const eventOptions = {
                        bubbles: true,
                        cancelable: true,
                        composed: true,
                        view: window,
                        clientX: x,
                        clientY: y,
                        screenX: x,
                        screenY: y,
                        button: 0,
                        buttons: 1,
                        pointerType: "mouse",
                        isPrimary: true,
                        pointerId: 1
                    };

                    eventTypes.forEach((type) => {
                        let event;
                        if (type.startsWith("pointer")) {
                            event = new PointerEvent(type, eventOptions);
                        } else if (type === "focus") {
                            event = new FocusEvent(type, { bubbles: false, cancelable: true });
                        } else {
                            event = new MouseEvent(type, eventOptions);
                        }
                        btn.dispatchEvent(event);
                    });
                    return true;
                }
                """,
                selector,
            )
        except Exception as e:
            self._logger.debug(f"事件派发失败: {e}")
            return False

    async def _screenshot(self, name: str) -> None:
        """保存截图（如果启用）"""
        if self.config.browser.save_screenshots:
            try:
                await self.session_manager.save_screenshot(
                    self.browser,
                    self.account.username,
                    name
                )
            except Exception as e:
                self._logger.warning(f"保存截图失败: {e}")

    async def _login(self) -> LoginResult:
        """执行登录"""
        self._set_state(UnlockState.LOGGING_IN)
        self._logger.info("开始登录")

        auth = TwitterAuth(
            browser=self.browser,
            username=self.account.username,
            password=self.account.password,
            totp_secret=self.account.totp_secret,
            email=self.account.email,
            solver=self.solver,
            token=self.account.token  # 新增: 传递 Token 以支持 Token 优先登录
        )

        result = await auth.login()
        await self._screenshot("after_login")

        return result

    async def _navigate_to_unlock(self) -> bool:
        """导航到解锁页面"""
        try:
            page = self.browser.page
            await self.browser.navigate(self.UNLOCK_URL)

            # 等待页面完全加载
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
                self._logger.debug("页面网络空闲")
            except Exception as e:
                self._logger.debug(f"等待 networkidle 超时: {e}")

            # 额外等待确保动态内容加载
            await asyncio.sleep(3)

            # 等待页面主要内容出现
            try:
                await page.wait_for_selector("body", state="visible", timeout=5000)
            except:
                pass

            await self._screenshot("unlock_page")

            # 检查当前 URL，确认导航成功
            current_url = page.url
            self._logger.info(f"当前页面 URL: {current_url}")

            return True
        except Exception as e:
            self._logger.error(f"导航到解锁页面失败: {e}")
            return False

    async def _click_start_unlock(self) -> bool:
        """
        点击开始解锁按钮

        该方法会多次尝试点击 Start 按钮，并等待页面变化。
        某些情况下可能需要多次点击才能进入验证码页面。
        """
        page = self.browser.page
        max_click_attempts = 3
        selector = self.SELECTORS["unlock_button"]

        # 先处理 Cloudflare 验证，再尝试点击 Start
        cloudflare = CloudflareHandler(
            browser=self.browser,
            solver=self.solver,
            account_id=self.account.username
        )
        if await cloudflare.check_cloudflare_block():
            self._logger.info("检测到 Cloudflare 验证，尝试处理...")
            if not await cloudflare.handle_cloudflare_block():
                self._logger.error("Cloudflare 验证未通过，停止点击 Start")
                return False

        for click_attempt in range(max_click_attempts):
            try:
                self._logger.info(f"尝试点击 Start 按钮 ({click_attempt + 1}/{max_click_attempts})")

                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.scroll_into_view_if_needed()
                await asyncio.sleep(0.2)

                # 记录点击前的 URL
                url_before = page.url

                clicked = False
                try:
                    await locator.click(timeout=5000)
                    clicked = True
                except Exception as e:
                    self._logger.debug(f"Start 标准点击失败: {e}")
                    try:
                        await locator.click(timeout=5000, force=True)
                        clicked = True
                    except Exception as e2:
                        self._logger.debug(f"Start 强制点击失败: {e2}")
                        if await self._dispatch_click_events(selector):
                            clicked = True

                if clicked:
                    self._logger.debug("Start 点击已触发")

                    # 等待页面响应
                    await asyncio.sleep(3)

                    # 等待网络空闲
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass

                    # 检查页面是否发生变化
                    url_after = page.url
                    self._logger.info(f"点击后 URL: {url_after}")

                    # 检查是否有验证码出现
                    captcha_iframe = await page.query_selector(self.SELECTORS["captcha_iframe"])
                    turnstile_iframe = await page.query_selector(self.SELECTORS["turnstile_iframe"])

                    if captcha_iframe or turnstile_iframe:
                        self._logger.info("检测到验证码 iframe，Start 点击成功")
                        return True

                    # 检查 URL 是否变化（可能已跳转到其他页面）
                    if url_after != url_before:
                        self._logger.info(f"页面 URL 已变化: {url_before} -> {url_after}")
                        return True

                    # 检查 Start 按钮是否还存在
                    start_button_still_exists = await page.query_selector(self.SELECTORS["unlock_button"])
                    if not start_button_still_exists:
                        self._logger.info("Start 按钮已消失，页面可能已更新")
                        return True

                    # 如果按钮还在，页面没变化，尝试再次点击
                    self._logger.warning("页面未发生变化，准备重试点击...")
                    await self._screenshot(f"start_click_retry_{click_attempt}")
                    await asyncio.sleep(2)
                else:
                    self._logger.warning("Start 点击失败，准备重试...")
                    await asyncio.sleep(2)

            except Exception as e:
                self._logger.debug(f"点击 Start 按钮出错: {e}")
                if click_attempt < max_click_attempts - 1:
                    await asyncio.sleep(2)
                    continue

        self._logger.warning("多次点击 Start 按钮后页面仍未变化")
        return False

    async def _wait_for_plugin(self) -> Tuple[bool, Optional[str]]:
        """
        等待 YesCaptcha 插件自动处理验证码

        Returns:
            (是否成功, 错误信息)
        """
        self._set_state(UnlockState.WAITING_PLUGIN)
        self._logger.info("等待 YesCaptcha 人机助手处理验证码...")

        page = self.browser.page
        max_wait_time = self.config.captcha.plugin_max_wait_time
        check_interval = 5  # 每 5 秒检查一次

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time

            if elapsed > max_wait_time:
                return False, f"等待插件处理超时 ({max_wait_time}s)"

            # 检查验证码 iframe 是否还存在
            captcha_iframe = await page.query_selector(self.SELECTORS["captcha_iframe"])
            turnstile_iframe = await page.query_selector(self.SELECTORS["turnstile_iframe"])

            if not captcha_iframe and not turnstile_iframe:
                self._logger.info("验证码 iframe 已消失，插件处理完成")
                await asyncio.sleep(2)  # 等待页面更新
                return True, None

            # 检查是否已跳转到首页
            current_url = page.url
            if "home" in current_url:
                self._logger.info("已跳转到首页，验证成功")
                return True, None

            # 检查是否有成功指示
            success_el = await page.query_selector(self.SELECTORS["success_indicator"])
            if success_el:
                self._logger.info("检测到成功指示器")
                return True, None

            self._logger.debug(f"等待插件处理... ({int(elapsed)}s/{max_wait_time}s)")
            await asyncio.sleep(check_interval)

    async def _detect_and_solve_captcha(self) -> Tuple[bool, Optional[str]]:
        """检测并求解验证码"""
        self._set_state(UnlockState.DETECTING_CAPTCHA)
        self._logger.info("检测验证码类型")

        page = self.browser.page

        # 等待页面稳定后再检测验证码
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass
        await asyncio.sleep(2)

        # 记录当前页面状态用于调试
        current_url = page.url
        self._logger.info(f"验证码检测页面 URL: {current_url}")

        # 插件模式：检测到验证码后等待插件处理
        if self.is_plugin_mode:
            # 检查是否有验证码需要处理
            captcha_iframe = await page.query_selector(self.SELECTORS["captcha_iframe"])
            turnstile_iframe = await page.query_selector(self.SELECTORS["turnstile_iframe"])

            if captcha_iframe or turnstile_iframe:
                self._logger.info("检测到验证码，等待插件自动处理...")
                await self._screenshot("captcha_detected_plugin_mode")
                return await self._wait_for_plugin()
            else:
                self._logger.info("未检测到验证码，可能已通过或不需要验证码")
                return True, None

        # API 模式：使用代码处理验证码
        captcha_detected = False

        # 使用懒加载获取 Handler
        turnstile_handler = self._get_turnstile_handler()
        arkose_handler = self._get_arkose_handler()

        for attempt in range(3):
            self._logger.debug(f"验证码检测尝试 {attempt + 1}/3")

            # 检测 Turnstile
            if await turnstile_handler.detect():
                captcha_detected = True
                self._set_state(UnlockState.SOLVING_TURNSTILE)
                self._logger.info("检测到 Turnstile，开始求解")
                await self._screenshot("turnstile_detected")

                success, error = await turnstile_handler.solve()
                if not success:
                    return False, f"Turnstile 求解失败: {error}"

                await self._screenshot("turnstile_solved")
                await asyncio.sleep(3)
                break

            # 检测 Arkose FunCaptcha
            if await arkose_handler.detect():
                captcha_detected = True
                self._set_state(UnlockState.SOLVING_ARKOSE)
                self._logger.info("检测到 Arkose FunCaptcha，开始求解")
                await self._screenshot("arkose_detected")

                success, error = await arkose_handler.solve()
                if not success:
                    return False, f"Arkose 求解失败: {error}"

                await self._screenshot("arkose_solved")
                await asyncio.sleep(3)
                break

            # 未检测到验证码，等待后重试
            if attempt < 2:
                self._logger.debug("未检测到验证码，等待后重试...")
                await asyncio.sleep(2)

        if not captcha_detected:
            self._logger.info("未检测到需要解决的验证码，可能已通过或页面不需要验证码")
            await self._screenshot("no_captcha_detected")

        return True, None

    async def _verify_unlock(self) -> Tuple[bool, Optional[str]]:
        """验证解锁是否成功"""
        self._set_state(UnlockState.VERIFYING)
        self._logger.info("验证解锁结果")

        page = self.browser.page

        # 等待页面稳定
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass
        await asyncio.sleep(2)

        # 记录当前 URL 用于调试
        current_url = page.url
        self._logger.info(f"验证页面 URL: {current_url}")
        await self._screenshot("verify_page")

        # 尝试点击继续按钮（多次尝试）
        for _ in range(3):
            try:
                continue_btn = await page.query_selector(self.SELECTORS["continue_button"])
                if continue_btn:
                    self._logger.info("找到继续按钮，点击...")
                    await continue_btn.click()
                    await asyncio.sleep(3)
                    break
            except:
                pass
            await asyncio.sleep(1)

        # 刷新当前 URL
        current_url = page.url
        self._logger.info(f"点击后 URL: {current_url}")

        # 检查是否到达首页
        try:
            await page.wait_for_url(
                lambda url: "home" in url or ("/x.com" in url and "access" not in url),
                timeout=15000
            )

            # 等待页面加载
            await page.wait_for_load_state("networkidle", timeout=10000)
            await asyncio.sleep(2)

            # 检查首页指示器
            indicator = await page.query_selector(self.SELECTORS["success_indicator"])
            if indicator:
                self._logger.info("检测到首页指示器，解锁成功")
                return True, None

        except Exception as e:
            self._logger.debug(f"等待首页超时: {e}")

        # 检查错误消息
        try:
            error_el = await page.query_selector(self.SELECTORS["error_message"])
            if error_el:
                error_text = await error_el.text_content()
                return False, f"页面错误: {error_text}"
        except:
            pass

        # 检查当前 URL（更新后的值）
        current_url = page.url
        self._logger.info(f"最终 URL: {current_url}")

        if "home" in current_url:
            return True, None
        elif "suspended" in current_url:
            return False, "账号已被封禁"
        elif "locked" in current_url:
            return False, "账号仍处于锁定状态"
        elif "access" in current_url:
            # 仍在解锁页面，检查是否有进展
            await self._screenshot("still_on_access_page")
            return False, "仍在解锁页面，可能需要更多操作"

        return False, f"无法确认解锁状态 (URL: {current_url})"

    async def _save_session(self) -> bool:
        """保存会话信息"""
        self._set_state(UnlockState.SAVING)
        self._logger.info("保存会话信息")

        try:
            # 保存 cookies
            if self.config.output.export_cookies:
                await self.session_manager.save_cookies(
                    self.browser,
                    self.account.username
                )

            # 保存最终截图
            await self._screenshot("success_final")

            # 保存结果
            await self.session_manager.save_result(
                account_id=self.account.username,
                success=True,
                message="解锁成功",
                extra_data={
                    "attempts": self._attempts,
                    "final_state": self._state.value,
                    "captcha_mode": self.config.captcha.mode,
                }
            )

            return True

        except Exception as e:
            self._logger.error(f"保存会话失败: {e}")
            return False

    async def detect_current_state(self) -> str:
        """
        检测当前页面状态

        Returns:
            状态字符串: SUCCESS, NEED_START, CAPTCHA_PRESENT, NEED_CONTINUE,
                       SUSPENDED, LOCKED, ON_ACCESS_PAGE, UNKNOWN
        """
        page = self.browser.page
        current_url = page.url

        self._logger.debug(f"检测页面状态，当前 URL: {current_url}")

        # 1. 检查是否在首页（已解锁）
        if "/home" in current_url:
            home_el = await page.query_selector(self.SELECTORS["success_indicator"])
            if home_el:
                return "SUCCESS"

        # 2. 检查是否在解锁页面
        if "/account/access" in current_url:
            # 检查是否有 Start 按钮
            start_btn = await page.query_selector(self.SELECTORS["unlock_button"])
            if start_btn:
                return "NEED_START"

            # 检查是否有验证码
            captcha = await page.query_selector(self.SELECTORS["captcha_iframe"])
            turnstile = await page.query_selector(self.SELECTORS["turnstile_iframe"])
            if captcha or turnstile:
                return "CAPTCHA_PRESENT"

            # 检查是否有 Continue 按钮
            continue_btn = await page.query_selector(self.SELECTORS["continue_button"])
            if continue_btn:
                return "NEED_CONTINUE"

            return "ON_ACCESS_PAGE"

        # 3. 检查账号状态
        if "suspended" in current_url:
            return "SUSPENDED"
        if "locked" in current_url:
            return "LOCKED"

        return "UNKNOWN"

    async def continue_from_current_state(self) -> UnlockResult:
        """
        从当前页面状态继续解锁流程

        该方法用于调试场景，无需从登录开始，直接从当前页面状态继续。

        Returns:
            解锁结果
        """
        self._logger.info("从当前状态继续解锁流程")

        # 1. 检测当前状态
        state = await self.detect_current_state()
        self._logger.info(f"检测到当前状态: {state}")

        # 2. 根据状态执行操作
        if state == "SUCCESS":
            self._logger.info("账号已解锁，无需操作")
            self._set_state(UnlockState.SUCCESS)
            return UnlockResult(
                success=True,
                account_id=self.account.username,
                message="账号已解锁",
                state=self._state,
                attempts=0
            )

        if state == "SUSPENDED":
            self._logger.error("账号已被封禁")
            self._set_state(UnlockState.FAILED)
            return UnlockResult(
                success=False,
                account_id=self.account.username,
                message="账号已被封禁",
                state=self._state,
                attempts=0
            )

        if state == "NEED_START":
            self._logger.info("需要点击 Start 按钮")
            await self._click_start_unlock()

            # 等待并重新检测
            await asyncio.sleep(2)
            state = await self.detect_current_state()

        if state in ["CAPTCHA_PRESENT", "ON_ACCESS_PAGE"]:
            self._logger.info("等待验证码处理...")
            captcha_success, captcha_error = await self._detect_and_solve_captcha()
            if not captcha_success:
                self._logger.warning(f"验证码处理失败: {captcha_error}")
                self._set_state(UnlockState.FAILED)
                return UnlockResult(
                    success=False,
                    account_id=self.account.username,
                    message=f"验证码处理失败: {captcha_error}",
                    state=self._state,
                    attempts=1
                )

            # 等待并重新检测
            await asyncio.sleep(2)
            state = await self.detect_current_state()

        if state == "NEED_CONTINUE":
            self._logger.info("需要点击 Continue 按钮")
            page = self.browser.page
            try:
                continue_btn = await page.query_selector(self.SELECTORS["continue_button"])
                if continue_btn:
                    await continue_btn.click()
                    await asyncio.sleep(3)
            except Exception as e:
                self._logger.warning(f"点击 Continue 按钮失败: {e}")

        # 3. 验证结果
        verify_success, verify_error = await self._verify_unlock()
        if verify_success:
            self._logger.info("解锁成功")
            self._set_state(UnlockState.SUCCESS)
            await self._save_session()
            return UnlockResult(
                success=True,
                account_id=self.account.username,
                message="解锁成功",
                state=self._state,
                attempts=1
            )
        else:
            self._logger.warning(f"验证失败: {verify_error}")
            self._set_state(UnlockState.FAILED)
            return UnlockResult(
                success=False,
                account_id=self.account.username,
                message=f"验证失败: {verify_error}",
                state=self._state,
                attempts=1
            )

    async def run(self) -> UnlockResult:
        """
        执行完整解锁流程

        Returns:
            解锁结果
        """
        self._logger.info(f"开始解锁流程: {self.account.username}")
        self._logger.info(f"验证码模式: {self.config.captcha.mode}")

        max_attempts = self.config.retry.max_attempts

        for attempt in range(1, max_attempts + 1):
            self._attempts = attempt
            self._logger.info(f"尝试 {attempt}/{max_attempts}")

            try:
                # 1. 登录
                login_result = await self._login()

                if login_result == LoginResult.SUCCESS:
                    self._logger.info("登录成功，账号无需解锁")
                    self._set_state(UnlockState.SUCCESS)
                    await self._save_session()
                    return UnlockResult(
                        success=True,
                        account_id=self.account.username,
                        message="登录成功，账号正常",
                        state=self._state,
                        attempts=attempt
                    )

                elif login_result == LoginResult.ACCOUNT_SUSPENDED:
                    self._set_state(UnlockState.FAILED)
                    return UnlockResult(
                        success=False,
                        account_id=self.account.username,
                        message="账号已被封禁",
                        state=self._state,
                        attempts=attempt
                    )

                elif login_result == LoginResult.FAILED:
                    self._logger.warning("登录失败，重试中...")
                    continue

                # 2. 导航到解锁页面
                if login_result in [LoginResult.NEED_UNLOCK, LoginResult.NEED_CAPTCHA]:
                    if not await self._navigate_to_unlock():
                        continue

                    # 点击开始按钮
                    await self._click_start_unlock()

                    # 3. 处理验证码
                    captcha_success, captcha_error = await self._detect_and_solve_captcha()
                    if not captcha_success:
                        self._logger.warning(f"验证码处理失败: {captcha_error}")
                        await self._screenshot("captcha_failed")
                        continue

                    # 4. 验证解锁
                    verify_success, verify_error = await self._verify_unlock()
                    if verify_success:
                        self._set_state(UnlockState.SUCCESS)
                        await self._save_session()
                        return UnlockResult(
                            success=True,
                            account_id=self.account.username,
                            message="解锁成功",
                            state=self._state,
                            attempts=attempt
                        )
                    else:
                        self._logger.warning(f"验证失败: {verify_error}")
                        await self._screenshot("verify_failed")
                        continue

            except Exception as e:
                self._logger.error(f"解锁流程异常: {e}")
                await self._screenshot("error")

                if attempt < max_attempts:
                    # 指数退避
                    delay = self.config.retry.delay_base * (2 ** (attempt - 1))
                    self._logger.info(f"等待 {delay} 秒后重试")
                    await asyncio.sleep(delay)

        # 所有尝试失败
        self._set_state(UnlockState.FAILED)
        await self.session_manager.save_result(
            account_id=self.account.username,
            success=False,
            message=f"解锁失败，已尝试 {max_attempts} 次",
            extra_data={
                "attempts": self._attempts,
                "final_state": self._state.value,
                "captcha_mode": self.config.captcha.mode,
            }
        )

        return UnlockResult(
            success=False,
            account_id=self.account.username,
            message=f"解锁失败，已尝试 {max_attempts} 次",
            state=self._state,
            attempts=self._attempts
        )


async def unlock_account(
    browser: BrowserManager,
    solver,  # YesCaptchaSolver 或 None
    session_manager: SessionManager,
    account: AccountInfo,
    config: AppConfig,
) -> UnlockResult:
    """
    解锁单个账号（便捷函数）

    Args:
        browser: 浏览器管理器
        solver: YesCaptcha 求解器（API 模式）或 None（插件模式）
        session_manager: 会话管理器
        account: 账号信息
        config: 应用配置

    Returns:
        解锁结果
    """
    flow = UnlockFlow(
        browser=browser,
        solver=solver,
        session_manager=session_manager,
        account=account,
        config=config,
    )

    return await flow.run()


__all__ = [
    "UnlockState",
    "UnlockResult",
    "UnlockFlow",
    "unlock_account",
]
