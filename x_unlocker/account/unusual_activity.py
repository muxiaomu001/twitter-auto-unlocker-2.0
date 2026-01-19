"""
异常活动验证处理模块

功能:
- 检测 X (Twitter) 的异常活动验证步骤
- 处理用户名/邮箱/手机号验证
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from ..utils.logger import get_logger
from ..utils.helpers import human_delay, HUMAN_DELAY_MIN, HUMAN_DELAY_MAX

if TYPE_CHECKING:
    from ..core.browser import BrowserManager


class UnusualActivityHandler:
    """异常活动验证处理器"""

    # 选择器 - 更新于 v1.5.2，匹配 Twitter 新页面结构
    SELECTORS = {
        # 输入框选择器 - 增加 email 类型和可见性过滤
        "unusual_activity_input": 'input[data-testid="ocfEnterTextTextInput"], input[name="text"], input[autocomplete="email"], input[type="text"]:visible',
        # 标题选择器 - 增加 "Verify your identity" 和 "Enter your email address"
        "unusual_activity_heading": 'text="Verify your identity", text="Enter your phone number or username", text="输入你的手机号码或用户名", text="Enter your phone number or email address", text="Enter your email address"',
        # 下一步按钮 - 增加 data-testid 选择器
        "next_button": 'button[data-testid="ocfEnterTextNextButton"], button[role="button"]:has-text("Next"), button[role="button"]:has-text("下一步"), button:has-text("Next")',
    }

    def __init__(
        self,
        browser: "BrowserManager",
        username: str,
        email: Optional[str] = None,
        account_id: Optional[str] = None
    ):
        """
        初始化处理器

        Args:
            browser: 浏览器管理器
            username: 用户名
            email: 关联邮箱（优先使用）
            account_id: 账号标识（用于日志）
        """
        self.browser = browser
        self.username = username
        self.email = email
        self._logger = get_logger(__name__, account_id=account_id or username)

    async def check_for_unusual_activity(self) -> bool:
        """
        检查是否出现了'异常活动'验证步骤

        Returns:
            是否需要处理异常活动验证
        """
        page = self.browser.page

        # 方法 1: 检查 URL 是否包含特定路径
        try:
            current_url = page.url
            if "login_challenge" in current_url or "account_duplication_check" in current_url:
                self._logger.debug(f"通过 URL 检测到异常活动验证: {current_url}")
                return True
        except:
            pass

        # 方法 2: 使用 JavaScript 检测页面文本内容（更可靠）
        try:
            indicators = await page.evaluate("""() => {
                const bodyText = document.body?.innerText?.toLowerCase() || '';
                return {
                    hasVerifyIdentity: bodyText.includes('verify your identity'),
                    hasEnterPhone: bodyText.includes('enter your phone number'),
                    hasEnterEmail: bodyText.includes('enter your email'),
                    hasUnusualActivity: bodyText.includes('unusual activity') || bodyText.includes('异常活动'),
                    hasVerifyYou: bodyText.includes("verify that it's you") || bodyText.includes('确认是你本人'),
                };
            }""")

            if any(indicators.values()):
                matched = [k for k, v in indicators.items() if v]
                self._logger.debug(f"通过页面文本检测到异常活动验证: {matched}")
                return True
        except Exception as e:
            self._logger.debug(f"JavaScript 检测失败: {e}")

        # 方法 3: 使用选择器检查标题（备用）
        try:
            heading = await page.query_selector(self.SELECTORS["unusual_activity_heading"])
            if heading:
                self._logger.debug("通过选择器检测到异常活动验证标题")
                return True
        except:
            pass

        return False

    async def _wait_and_click(self, selector: str, timeout: int = 10000) -> bool:
        """等待元素并点击"""
        try:
            element = await self.browser.page.wait_for_selector(
                selector,
                timeout=timeout,
                state="visible"
            )
            if element:
                await element.click()
                await asyncio.sleep(0.5)
                return True
        except Exception as e:
            self._logger.debug(f"等待元素 {selector} 超时: {e}")
        return False

    async def handle_unusual_activity(self) -> bool:
        """
        处理'异常活动'验证步骤

        当 X 怀疑自动化时，会要求用户再次确认用户名、电话号码或邮箱。
        根据页面提示智能选择输入内容。

        Returns:
            是否成功处理
        """
        page = self.browser.page

        # 检测页面要求的验证类型
        try:
            page_text = await page.evaluate("() => document.body?.innerText?.toLowerCase() || ''")

            # 如果页面要求 "手机号或用户名"，优先使用用户名
            if "phone number or username" in page_text or "手机号码或用户名" in page_text:
                verification_value = self.username
                self._logger.info(f"页面要求手机号或用户名，使用用户名: {verification_value}")
            # 如果页面要求 "邮箱"，使用邮箱
            elif "email" in page_text or "邮箱" in page_text:
                verification_value = self.email if self.email else self.username
                self._logger.info(f"页面要求邮箱，使用: {verification_value[:10]}...")
            else:
                # 默认使用用户名（更安全）
                verification_value = self.username
                self._logger.info(f"默认使用用户名: {verification_value}")
        except Exception as e:
            self._logger.debug(f"检测页面类型失败: {e}，默认使用用户名")
            verification_value = self.username

        self._logger.info(f"检测到异常活动验证，尝试输入: {verification_value[:10]}...")

        try:
            # 等待页面完全加载
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass

            # 额外等待 - 确保 JavaScript 渲染完成
            await asyncio.sleep(2)

            # 先截图记录当前页面状态
            try:
                from pathlib import Path
                output_dir = Path("output/debug")
                output_dir.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(output_dir / "unusual_activity_page.png"))
                self._logger.debug("已保存异常活动页面截图")
            except Exception as e:
                self._logger.debug(f"保存截图失败: {e}")

            # 输出页面标题和 URL 用于调试
            try:
                title = await page.title()
                url = page.url
                self._logger.debug(f"当前页面: {title} | URL: {url}")
            except:
                pass

            # 尝试多种选择器来找到输入框（按优先级排序）
            input_selectors = [
                # 优先使用 Twitter 特定的 data-testid
                'input[data-testid="ocfEnterTextTextInput"]',
                # Email 相关选择器
                'input[autocomplete="email"]',
                'input[type="email"]',
                'input[name="email"]',
                # 通用文本输入框
                'input[name="text"]',
                'input[autocomplete="on"]',
                'input[autocomplete="username"]',
                'input[autocomplete="tel"]',
                # 更宽泛的选择器
                'input[type="text"]:not([name="password"]):not([type="hidden"])',
                # 最宽泛的选择器（排除不需要的类型）
                'input:not([type="hidden"]):not([type="password"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"])',
            ]

            input_el = None
            for selector in input_selectors:
                try:
                    input_el = await page.wait_for_selector(
                        selector,
                        timeout=3000,
                        state="visible"
                    )
                    if input_el:
                        self._logger.debug(f"使用选择器找到输入框: {selector}")
                        break
                except:
                    continue

            if input_el:
                # 输入验证值（邮箱或用户名）
                await human_delay(0.5, 1.0)
                await input_el.click()
                await asyncio.sleep(0.2)
                await input_el.fill("")  # 清空
                await input_el.type(verification_value, delay=50)

                self._logger.debug(f"已输入验证值: {verification_value}")

                # 点击下一步
                await human_delay(0.3, 0.8)
                await self._wait_and_click(self.SELECTORS["next_button"])
                await human_delay(2, 3)

                self._logger.info("异常活动验证步骤完成")
                return True
            else:
                self._logger.warning("未能找到异常活动验证的输入框")
                # 尝试使用 JavaScript 查找并输出更详细的调试信息
                try:
                    debug_info = await page.evaluate("""
                        () => {
                            const inputs = document.querySelectorAll('input');
                            const inputInfo = [];
                            inputs.forEach((input, i) => {
                                inputInfo.push({
                                    index: i,
                                    type: input.type,
                                    name: input.name,
                                    id: input.id,
                                    placeholder: input.placeholder,
                                    autocomplete: input.autocomplete,
                                    visible: input.offsetParent !== null,
                                    testid: input.getAttribute('data-testid')
                                });
                            });
                            return {
                                inputCount: inputs.length,
                                inputs: inputInfo,
                                bodyText: document.body.innerText.substring(0, 500)
                            };
                        }
                    """)
                    self._logger.debug(f"页面上找到 {debug_info['inputCount']} 个输入框")
                    self._logger.debug(f"输入框详情: {debug_info['inputs']}")
                    self._logger.debug(f"页面文本: {debug_info['bodyText'][:200]}...")
                except Exception as e:
                    self._logger.debug(f"获取调试信息失败: {e}")
                return False

        except Exception as e:
            self._logger.error(f"处理异常活动验证失败: {e}")

        return False
