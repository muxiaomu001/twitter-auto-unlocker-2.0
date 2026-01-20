#!/usr/bin/env python3
"""
调试脚本 - 连接到现有比特浏览器窗口继续解锁流程

Usage:
    python scripts/debug_unlock.py --browser-id <BROWSER_ID>
    python scripts/debug_unlock.py --browser-id effb62a3e4d54b3ca8ba8c759d84fc0e

功能:
- 连接到指定的比特浏览器窗口（不创建新配置）
- 自动检测当前页面状态
- 从当前状态继续执行解锁流程
- 使用真实鼠标轨迹模拟点击（贝塞尔曲线）
- 等待 YesCaptcha 插件处理验证码
- 验证解锁结果并保存 Cookies
"""

import argparse
import asyncio
import random
import math
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from x_unlocker.core.bitbrowser_provider import BitBrowserProvider
from x_unlocker.captcha.plugin_config import apply_captcha_plugin_config
from x_unlocker.core.config import load_config
from x_unlocker.core.session import SessionManager
from x_unlocker.utils.logger import get_logger, setup_main_logger

logger = get_logger(__name__)


# ============================================================================
# 隐身脚本 - 消除 Playwright/CDP 指纹特征
# ============================================================================
STEALTH_JS = r"""
// 隐藏 webdriver 属性
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});

// 伪装 chrome 对象
Object.defineProperty(window, 'chrome', {
    get: () => ({
        app: { isInstalled: false },
        webstore: { onInstallStageChanged: null, onDownloadProgress: null },
        runtime: { id: undefined }
    }),
    configurable: true
});

// 伪装 plugins（正常浏览器有多个插件）
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' }
        ];
        plugins.length = 3;
        return plugins;
    },
    configurable: true
});

// 伪装语言设置
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'zh-CN', 'zh'],
    configurable: true
});

// 伪装硬件并发数
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true
});

// 伪装设备内存
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true
});

// 修复 permissions 查询
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => {
    if (parameters.name === 'notifications') {
        return Promise.resolve({ state: 'denied', onchange: null });
    }
    return originalQuery.call(window.navigator.permissions, parameters);
};

// 修复屏幕尺寸一致性
Object.defineProperty(screen, 'availHeight', {
    get: () => screen.height - 40,
    configurable: true
});
Object.defineProperty(screen, 'availWidth', {
    get: () => screen.width,
    configurable: true
});

// 移除 Playwright 注入的属性
delete window.__playwright;
delete window.__pw_manual;
delete window.__PW_inspect;

console.log('[Stealth] Anti-detection patches applied');
"""


def bezier_curve(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    """
    计算三次贝塞尔曲线上的点

    Args:
        t: 参数 [0, 1]
        p0, p1, p2, p3: 控制点 (x, y)

    Returns:
        曲线上的点 (x, y)
    """
    x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
    y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
    return (x, y)


def generate_human_path(start: tuple, end: tuple, num_points: int = 50) -> list:
    """
    生成模拟人类鼠标移动的路径点

    使用贝塞尔曲线 + 随机偏移模拟真实鼠标轨迹

    Args:
        start: 起点 (x, y)
        end: 终点 (x, y)
        num_points: 路径点数量

    Returns:
        路径点列表 [(x, y), ...]
    """
    # 计算距离
    distance = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)

    # 根据距离调整控制点偏移量
    offset_range = min(distance * 0.3, 100)  # 最大偏移不超过100像素

    # 生成随机控制点（模拟人类鼠标移动的弧度）
    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2

    # 控制点1：靠近起点，有随机偏移
    ctrl1 = (
        start[0] + (end[0] - start[0]) * 0.25 + random.uniform(-offset_range, offset_range),
        start[1] + (end[1] - start[1]) * 0.25 + random.uniform(-offset_range, offset_range)
    )

    # 控制点2：靠近终点，有随机偏移
    ctrl2 = (
        start[0] + (end[0] - start[0]) * 0.75 + random.uniform(-offset_range, offset_range),
        start[1] + (end[1] - start[1]) * 0.75 + random.uniform(-offset_range, offset_range)
    )

    # 生成路径点
    path = []
    for i in range(num_points):
        t = i / (num_points - 1)

        # 使用 ease-out 缓动函数使移动更自然（开始快，结束慢）
        t_eased = 1 - (1 - t) ** 2

        point = bezier_curve(t_eased, start, ctrl1, ctrl2, end)

        # 添加微小的随机抖动（模拟手抖）
        jitter = 0.5 if i > 0 and i < num_points - 1 else 0
        point = (
            point[0] + random.uniform(-jitter, jitter),
            point[1] + random.uniform(-jitter, jitter)
        )

        path.append(point)

    return path


async def human_mouse_move(page, target_x: float, target_y: float):
    """
    模拟人类鼠标移动到目标位置

    Args:
        page: Playwright 页面对象
        target_x: 目标 X 坐标
        target_y: 目标 Y 坐标
    """
    # 获取当前鼠标位置（默认从页面中心开始）
    try:
        viewport = page.viewport_size
        current_x = viewport['width'] / 2
        current_y = viewport['height'] / 2
    except:
        current_x = 500
        current_y = 300

    # 生成人类化路径
    path = generate_human_path(
        (current_x, current_y),
        (target_x, target_y),
        num_points=random.randint(30, 50)
    )

    # 沿路径移动鼠标
    for point in path:
        await page.mouse.move(point[0], point[1])
        # 随机延迟模拟人类速度变化
        await asyncio.sleep(random.uniform(0.001, 0.008))


async def human_click(page, x: float, y: float):
    """
    模拟人类点击（移动 + 点击 + 随机延迟）

    Args:
        page: Playwright 页面对象
        x: 点击 X 坐标
        y: 点击 Y 坐标
    """
    # 先移动到目标位置
    await human_mouse_move(page, x, y)

    # 点击前的微小延迟
    await asyncio.sleep(random.uniform(0.05, 0.15))

    # 点击
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.05, 0.12))  # 按下持续时间
    await page.mouse.up()

    # 点击后的短暂停留
    await asyncio.sleep(random.uniform(0.1, 0.3))


class UnlockDebugger:
    """解锁流程调试器"""

    # 选择器
    SELECTORS = {
        # Start 按钮
        "start_button": 'button[data-testid="ocfStartButton"], button:has-text("Start"), button:has-text("开始")',
        # Continue 按钮
        "continue_button": 'button[data-testid="ocfVerifySuccessNextButton"], button:has-text("Continue"), button:has-text("Continue to X"), button:has-text("继续"), a:has-text("Continue"), a:has-text("Continue to X"), [role="button"]:has-text("Continue"), [role="button"]:has-text("Continue to X")',
        # 成功指示器
        "home_indicator": '[data-testid="primaryColumn"]',
        # 验证码 iframe
        "captcha_iframe": 'iframe[src*="arkoselabs"], iframe[src*="funcaptcha"], iframe[id*="arkose"]',
        "turnstile_iframe": 'iframe[src*="turnstile"], iframe[src*="cloudflare"], iframe[src*="challenges.cloudflare.com"]',
        # Turnstile 验证框内的复选框（用于点击）
        "turnstile_checkbox": 'input[type="checkbox"], .cb-lb, #cf-stage',
        # 锁定页面
        "locked_title": 'h1:has-text("Your account has been locked"), h1:has-text("账号已被锁定")',
        "challenge_text": ':text("Pass a challenge"), :text("通过验证")',
        # 错误消息
        "error_message": '[data-testid="error-detail"]',
        # 页面加载错误（Something went wrong）
        "page_error": ':text("Something went wrong"), :text("出错了")',
        "retry_button": 'button:has-text("Retry"), button:has-text("重试"), [role="button"]:has-text("Try again")',
    }

    def __init__(self, browser: BitBrowserProvider, config=None):
        self.browser = browser
        self.config = config
        self._logger = logger

    async def _find_frame_with_selector(self, selector: str):
        """在主文档与子 frame 中查找元素"""
        page = self.browser.page
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames:
            try:
                el = await frame.query_selector(selector)
                if el:
                    return frame
            except Exception:
                continue
        return None

    async def _find_frame_with_text(self, text: str):
        """在主文档与子 frame 中查找文本"""
        page = self.browser.page
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames:
            try:
                locator = frame.get_by_text(text, exact=True)
                if await locator.count() > 0:
                    return frame
            except Exception:
                continue
        return None

    async def _click_by_text(self, texts: list[str]) -> bool:
        """兜底：用文本匹配点击按钮"""
        page = self.browser.page
        try:
            return await page.evaluate(
                """
                (texts) => {
                    const candidates = Array.from(document.querySelectorAll(
                        'button,[role="button"],a,div'
                    ));
                    const normalized = (s) => (s || '').trim();
                    for (const el of candidates) {
                        const txt = normalized(el.innerText);
                        if (!txt) continue;
                        if (texts.some(t => txt.startsWith(t))) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                """,
                texts,
            )
        except Exception:
            return False

    async def detect_state(self) -> str:
        """检测当前页面状态"""
        page = self.browser.page
        current_url = page.url

        self._logger.info(f"当前 URL: {current_url}")

        # 保存截图用于调试
        try:
            output_dir = project_root / "output" / "debug"
            output_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(output_dir / "current_state.png"))
            self._logger.info(f"截图已保存到: {output_dir / 'current_state.png'}")
        except Exception as e:
            self._logger.warning(f"保存截图失败: {e}")

        # 0. 检查页面是否出现错误（Something went wrong）
        try:
            page_error = await page.query_selector(self.SELECTORS["page_error"])
            if page_error:
                self._logger.warning("检测到页面错误: Something went wrong")
                return "PAGE_ERROR"
        except Exception:
            pass

        # 1. 检查是否在首页（已解锁）
        if "/home" in current_url:
            home_el = await page.query_selector(self.SELECTORS["home_indicator"])
            if home_el:
                return "SUCCESS"

        # 2. 检查是否在解锁页面
        if "/account/access" in current_url:
            # 优先检查是否已出现验证码（避免 Start 仍在 DOM 时误判）
            captcha_frame = await self._find_frame_with_selector(self.SELECTORS["captcha_iframe"])
            turnstile_frame = await self._find_frame_with_selector(self.SELECTORS["turnstile_iframe"])
            if captcha_frame or turnstile_frame:
                return "CAPTCHA_PRESENT"

            # 检查是否有 Start 按钮 - 尝试多种选择器
            start_selectors = [
                'button[data-testid="ocfStartButton"]',
                'button:has-text("Start")',
                'button:has-text("开始")',
                '[role="button"]:has-text("Start")',
                'div[role="button"]:has-text("Start")',
            ]

            for selector in start_selectors:
                try:
                    start_frame = await self._find_frame_with_selector(selector)
                    if start_frame:
                        self._logger.info(f"找到 Start 按钮 (选择器: {selector})")
                        return "NEED_START"
                except Exception as e:
                    self._logger.debug(f"选择器 {selector} 检测失败: {e}")

            # 兜底：通过文本检测 Start
            for text in ["Start", "开始"]:
                start_frame = await self._find_frame_with_text(text)
                if start_frame:
                    self._logger.info(f"找到 Start 文本 (text={text})")
                    return "NEED_START"

            # 兜底：如果锁定标题存在，仍然认为需要 Start
            try:
                locked_title = await page.query_selector(self.SELECTORS["locked_title"])
                if locked_title:
                    self._logger.info("检测到锁定标题，推断需要 Start")
                    return "NEED_START"
            except Exception:
                pass

            # 检查是否有 Continue 按钮
            continue_frame = await self._find_frame_with_selector(self.SELECTORS["continue_button"])
            if continue_frame:
                return "NEED_CONTINUE"

            # 兜底：通过文本检测 Continue
            for text in ["Continue to X", "Continue", "继续"]:
                continue_frame = await self._find_frame_with_text(text)
                if continue_frame:
                    self._logger.info(f"找到 Continue 文本 (text={text})")
                    return "NEED_CONTINUE"

            # 输出页面内容用于调试
            try:
                buttons = await page.query_selector_all('button')
                self._logger.info(f"页面上共有 {len(buttons)} 个按钮")
                for i, btn in enumerate(buttons[:5]):  # 只显示前5个
                    text = await btn.text_content()
                    self._logger.info(f"  按钮 {i}: {text[:50] if text else 'N/A'}")
            except Exception as e:
                self._logger.debug(f"获取按钮列表失败: {e}")

            return "ON_ACCESS_PAGE"

        # 3. 检查账号状态
        if "suspended" in current_url:
            return "SUSPENDED"
        if "locked" in current_url:
            return "LOCKED"

        return "UNKNOWN"

    async def click_start(self) -> bool:
        """
        点击 Start 按钮（增强版：行为预热 + 人类化轨迹 + 兜底事件派发）

        改进点：
        1. 页面行为预热（随机移动 + 轻微滚动）
        2. 悬停预热后再点击
        3. 安全点击区域（避开边缘）
        4. 延长等待时间
        5. 兜底 JavaScript 事件派发
        """
        page = self.browser.page
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                self._logger.info(f"尝试点击 Start 按钮 ({attempt + 1}/{max_attempts})")

                # ===== 步骤 1：行为预热（模拟真实用户阅读页面） =====
                self._logger.debug("执行行为预热...")

                # 1a. 页面随机移动（模拟用户浏览）
                try:
                    viewport = page.viewport_size or {"width": 1280, "height": 800}
                    warmup_x = random.randint(100, min(400, viewport["width"] - 100))
                    warmup_y = random.randint(100, min(300, viewport["height"] - 100))
                    await page.mouse.move(warmup_x, warmup_y, steps=random.randint(20, 35))
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                except Exception as e:
                    self._logger.debug(f"预热移动出错: {e}")

                # 1b. 轻微滚动（模拟阅读）
                try:
                    await page.mouse.wheel(0, random.randint(30, 120))
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await page.mouse.wheel(0, -random.randint(10, 50))  # 滚回一点
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                except Exception as e:
                    self._logger.debug(f"预热滚动出错: {e}")

                # ===== 步骤 2：定位并准备点击按钮 =====
                target_frame = await self._find_frame_with_selector(self.SELECTORS["start_button"])
                if not target_frame:
                    for text in ["Start", "开始"]:
                        target_frame = await self._find_frame_with_text(text)
                        if target_frame:
                            break
                if not target_frame:
                    target_frame = page.main_frame

                # 使用 locator API（更稳定）
                btn_locator = target_frame.locator(self.SELECTORS["start_button"]).first
                if await btn_locator.count() == 0:
                    btn_locator = target_frame.get_by_text("Start", exact=True).first
                    if await btn_locator.count() == 0:
                        btn_locator = target_frame.get_by_text("开始", exact=True).first
                await btn_locator.wait_for(state="visible", timeout=10000)

                # 确保按钮在视口内
                await btn_locator.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.2, 0.4))

                # ===== 步骤 3：悬停预热 =====
                self._logger.debug("执行悬停预热...")
                await btn_locator.hover()
                await asyncio.sleep(random.uniform(0.15, 0.35))

                # ===== 步骤 4：计算安全点击区域（避开边缘） =====
                bounding_box = await btn_locator.bounding_box()
                if not bounding_box:
                    self._logger.warning("无法获取按钮边界框")
                    continue

                url_before = page.url

                # 点击区域：按钮中心 35%-65% 水平，45%-70% 垂直（避开边缘阴影）
                target_x = bounding_box["x"] + bounding_box["width"] * random.uniform(0.35, 0.65)
                target_y = bounding_box["y"] + bounding_box["height"] * random.uniform(0.45, 0.70)

                self._logger.info(f"使用增强人类化点击 Start 按钮 (x={target_x:.1f}, y={target_y:.1f})")

                # ===== 步骤 5：人类化移动并点击 =====
                await human_mouse_move(page, target_x, target_y)

                # 点击前微停顿
                await asyncio.sleep(random.uniform(0.05, 0.12))

                # 执行点击
                await page.mouse.down()
                await asyncio.sleep(random.uniform(0.06, 0.14))  # 按下持续时间
                await page.mouse.up()

                self._logger.debug("Start 按钮已点击")

                # ===== 步骤 6：等待响应（延长到 5-8s） =====
                await asyncio.sleep(random.uniform(5, 8))

                # 等待网络空闲
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                # ===== 步骤 7：检查是否有变化 =====
                url_after = page.url
                if url_after != url_before:
                    self._logger.info(f"URL 已变化: {url_before} -> {url_after}")
                    return True

                # 检查验证码是否出现
                captcha = await page.query_selector(self.SELECTORS["captcha_iframe"])
                turnstile = await page.query_selector(self.SELECTORS["turnstile_iframe"])
                if captcha or turnstile:
                    self._logger.info("检测到验证码 iframe")
                    return True

                # 检查按钮是否消失
                btn_still = await page.query_selector(self.SELECTORS["start_button"])
                if not btn_still:
                    self._logger.info("Start 按钮已消失")
                    return True

                # ===== 步骤 8：兜底 - JavaScript 事件派发 =====
                self._logger.warning("CDP 点击无效，尝试 JavaScript 事件派发...")
                dispatch_result = await self._dispatch_click_events(page, self.SELECTORS["start_button"])

                if dispatch_result:
                    await asyncio.sleep(random.uniform(3, 5))

                    # 再次检查变化
                    captcha = await page.query_selector(self.SELECTORS["captcha_iframe"])
                    turnstile = await page.query_selector(self.SELECTORS["turnstile_iframe"])
                    if captcha or turnstile:
                        self._logger.info("事件派发后检测到验证码 iframe")
                        return True

                    btn_still = await page.query_selector(self.SELECTORS["start_button"])
                    if not btn_still:
                        self._logger.info("事件派发后 Start 按钮已消失")
                        return True

                # ===== 步骤 9：尝试刷新页面 =====
                self._logger.info("点击和事件派发均无效，尝试刷新页面...")
                await page.reload(wait_until="networkidle")
                await asyncio.sleep(3)

                # 刷新后检查状态
                captcha = await page.query_selector(self.SELECTORS["captcha_iframe"])
                turnstile = await page.query_selector(self.SELECTORS["turnstile_iframe"])
                if captcha or turnstile:
                    self._logger.info("刷新后检测到验证码 iframe")
                    return True

                btn_still = await page.query_selector(self.SELECTORS["start_button"])
                if not btn_still:
                    self._logger.info("刷新后 Start 按钮已消失")
                    return True

                # ===== 步骤 10：兜底 - 文本匹配点击 =====
                if await self._click_by_text(["Start", "开始"]):
                    self._logger.info("文本匹配点击已触发")
                    await asyncio.sleep(3)
                    captcha = await page.query_selector(self.SELECTORS["captcha_iframe"])
                    turnstile = await page.query_selector(self.SELECTORS["turnstile_iframe"])
                    if captcha or turnstile:
                        self._logger.info("文本点击后检测到验证码 iframe")
                        return True

                self._logger.warning("刷新后仍无变化，重试...")
                await asyncio.sleep(2)

            except Exception as e:
                self._logger.warning(f"点击出错: {e}")
                import traceback
                self._logger.debug(traceback.format_exc())
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)

        return False

    async def _dispatch_click_events(self, page, selector: str) -> bool:
        """
        使用 JavaScript 派发完整的指针事件链

        当 CDP 模拟点击被反爬检测阻止时，尝试直接派发 DOM 事件
        """
        try:
            result = await page.evaluate("""
            (selector) => {
                // 查找按钮元素
                const btn = document.querySelector(selector);
                if (!btn) {
                    console.log('[Dispatch] 未找到按钮:', selector);
                    return false;
                }

                // 获取按钮中心坐标
                const rect = btn.getBoundingClientRect();
                const x = rect.left + rect.width * 0.5;
                const y = rect.top + rect.height * 0.6;

                console.log('[Dispatch] 按钮位置:', rect, '点击坐标:', x, y);

                // 完整的事件链（模拟真实鼠标交互）
                const eventTypes = [
                    'pointerover', 'pointerenter',
                    'mouseover', 'mouseenter',
                    'pointermove', 'mousemove',
                    'pointerdown', 'mousedown',
                    'focus',
                    'pointerup', 'mouseup',
                    'click'
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
                    pointerType: 'mouse',
                    isPrimary: true,
                    pointerId: 1
                };

                eventTypes.forEach(type => {
                    let event;
                    if (type.startsWith('pointer')) {
                        event = new PointerEvent(type, eventOptions);
                    } else if (type === 'focus') {
                        event = new FocusEvent(type, { bubbles: false, cancelable: true });
                    } else {
                        event = new MouseEvent(type, eventOptions);
                    }
                    btn.dispatchEvent(event);
                });

                console.log('[Dispatch] 事件链派发完成');
                return true;
            }
            """, selector)

            if result:
                self._logger.info("JavaScript 事件链派发成功")
            else:
                self._logger.warning("JavaScript 事件链派发失败：未找到按钮")

            return result

        except Exception as e:
            self._logger.error(f"事件派发出错: {e}")
            return False

    async def wait_for_captcha(self, max_wait: int = 180) -> bool:
        """等待验证码处理（YesCaptcha 插件模式 + Turnstile 手动点击）"""
        page = self.browser.page
        check_interval = 5
        elapsed = 0
        turnstile_clicked = False

        self._logger.info(f"等待验证码处理 (最多 {max_wait}s)...")

        while elapsed < max_wait:
            # 检查验证码是否还存在
            captcha = await page.query_selector(self.SELECTORS["captcha_iframe"])
            turnstile = await page.query_selector(self.SELECTORS["turnstile_iframe"])

            if not captcha and not turnstile:
                self._logger.info("验证码 iframe 已消失")
                await asyncio.sleep(2)
                return True

            # 如果检测到 Turnstile 且未点击过，尝试点击
            if turnstile and not turnstile_clicked:
                self._logger.info("检测到 Cloudflare Turnstile，尝试手动点击...")
                if await self.click_turnstile():
                    turnstile_clicked = True
                    # 点击后等待更长时间
                    await asyncio.sleep(5)
                    continue

            # 检查是否跳转到首页
            current_url = page.url
            if "/home" in current_url:
                self._logger.info("已跳转到首页")
                return True

            # 检查 Continue 按钮
            continue_btn = await page.query_selector(self.SELECTORS["continue_button"])
            if continue_btn:
                self._logger.info("检测到 Continue 按钮")
                return True

            self._logger.debug(f"等待验证码处理... ({elapsed}s/{max_wait}s)")
            await asyncio.sleep(check_interval)
            elapsed += check_interval

        return False

    async def click_continue(self) -> bool:
        """点击 Continue 按钮（使用人类化鼠标轨迹）"""
        page = self.browser.page

        for attempt in range(3):
            try:
                target_frame = await self._find_frame_with_selector(self.SELECTORS["continue_button"])
                if not target_frame:
                    for text in ["Continue to X", "Continue", "继续"]:
                        target_frame = await self._find_frame_with_text(text)
                        if target_frame:
                            break
                if not target_frame:
                    target_frame = page.main_frame

                continue_btn = await target_frame.query_selector(self.SELECTORS["continue_button"])
                if not continue_btn:
                    locator = target_frame.get_by_text("Continue to X", exact=True)
                    if await locator.count() == 0:
                        locator = target_frame.get_by_text("Continue", exact=True)
                    if await locator.count() > 0:
                        await locator.first.click()
                        await asyncio.sleep(3)
                        return True

                if continue_btn:
                    self._logger.info("点击 Continue 按钮...")

                    # 获取按钮边界框
                    bounding_box = await continue_btn.bounding_box()
                    if bounding_box:
                        # 计算按钮中心点（带随机偏移）
                        click_x = bounding_box['x'] + bounding_box['width'] / 2 + random.uniform(-5, 5)
                        click_y = bounding_box['y'] + bounding_box['height'] / 2 + random.uniform(-3, 3)

                        self._logger.info(f"使用人类化鼠标轨迹点击 Continue (x={click_x:.1f}, y={click_y:.1f})")

                        # 使用人类化点击
                        await human_click(page, click_x, click_y)
                    else:
                        # 回退到普通点击
                        await continue_btn.click()

                    await asyncio.sleep(3)
                    return True
            except Exception as e:
                self._logger.debug(f"点击 Continue 出错: {e}")
            await asyncio.sleep(1)

        return False

    async def click_turnstile(self) -> bool:
        """
        点击 Cloudflare Turnstile 验证框（使用人类化鼠标轨迹）

        YesCaptcha 插件无法自动处理 Turnstile，需要模拟真实鼠标点击验证框
        """
        page = self.browser.page

        self._logger.info("尝试点击 Cloudflare Turnstile 验证框...")

        try:
            # 查找 Turnstile iframe
            turnstile_iframe = await page.query_selector(self.SELECTORS["turnstile_iframe"])

            if not turnstile_iframe:
                self._logger.debug("未找到 Turnstile iframe")
                return False

            # 获取 iframe 的边界框
            bounding_box = await turnstile_iframe.bounding_box()
            if not bounding_box:
                self._logger.warning("无法获取 Turnstile iframe 边界框")
                return False

            self._logger.info(f"Turnstile iframe 位置: x={bounding_box['x']}, y={bounding_box['y']}, "
                            f"width={bounding_box['width']}, height={bounding_box['height']}")

            # 计算验证框中心点（通常在 iframe 左侧约 30-40px 处）
            # 添加随机偏移使点击更自然
            click_x = bounding_box['x'] + 35 + random.uniform(-3, 3)
            click_y = bounding_box['y'] + bounding_box['height'] / 2 + random.uniform(-3, 3)

            self._logger.info(f"使用人类化鼠标轨迹点击 Turnstile (x={click_x:.1f}, y={click_y:.1f})")

            # 使用人类化点击
            await human_click(page, click_x, click_y)

            self._logger.info("已点击 Turnstile 验证框")

            # 等待验证处理
            await asyncio.sleep(3)

            return True

        except Exception as e:
            self._logger.error(f"点击 Turnstile 验证框失败: {e}")
            return False

    async def verify_success(self) -> bool:
        """验证解锁是否成功"""
        page = self.browser.page

        # 等待页面稳定
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(2)

        current_url = page.url
        self._logger.info(f"验证页面 URL: {current_url}")

        # 检查是否到达首页
        if "/home" in current_url:
            home_el = await page.query_selector(self.SELECTORS["home_indicator"])
            if home_el:
                return True

        # 检查错误消息
        error_el = await page.query_selector(self.SELECTORS["error_message"])
        if error_el:
            error_text = await error_el.text_content()
            self._logger.error(f"页面错误: {error_text}")
            return False

        return False

    async def save_cookies(self, account_id: str, output_dir: Path) -> bool:
        """保存 Cookies"""
        try:
            cookies = await self.browser.context.cookies()
            cookies_file = output_dir / f"{account_id}.json"

            import json
            with open(cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2, ensure_ascii=False)

            self._logger.info(f"Cookies 已保存到: {cookies_file}")
            return True
        except Exception as e:
            self._logger.error(f"保存 Cookies 失败: {e}")
            return False

    async def run(self) -> bool:
        """执行完整的调试流程（带网络监听诊断）"""
        page = self.browser.page

        # ===== 设置诊断监听器 =====
        console_logs = []
        network_errors = []

        def on_console(msg):
            """捕获控制台日志"""
            if msg.type in ["error", "warning"]:
                console_logs.append(f"[{msg.type}] {msg.text}")
                # 检查是否有 automation 相关错误
                if "automation" in msg.text.lower() or "bot" in msg.text.lower():
                    self._logger.warning(f"[Console] 检测到反爬相关日志: {msg.text}")

        def on_response(response):
            """捕获网络响应（特别关注 flow 请求）"""
            url = response.url
            status = response.status
            # 关注 Twitter API 请求
            if "api." in url or "flow" in url or "account" in url:
                if status >= 400:
                    error_info = f"[{status}] {url}"
                    network_errors.append(error_info)
                    self._logger.warning(f"[Network] API 错误响应: {error_info}")
                elif "flow" in url:
                    self._logger.debug(f"[Network] Flow 请求: [{status}] {url}")

        # 注册监听器
        page.on("console", on_console)
        page.on("response", on_response)

        try:
            # 1. 检测当前状态
            state = await self.detect_state()
            self._logger.info(f"检测到状态: {state}")

            # 处理页面错误（Something went wrong）
            if state == "PAGE_ERROR":
                self._logger.info("页面出错，尝试刷新...")
                for retry in range(3):
                    await page.reload(wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(3)
                    state = await self.detect_state()
                    if state != "PAGE_ERROR":
                        self._logger.info(f"刷新后状态: {state}")
                        break
                    self._logger.warning(f"刷新第 {retry + 1} 次后仍显示错误，继续重试...")

                if state == "PAGE_ERROR":
                    self._logger.error("多次刷新后仍显示页面错误")
                    return False

            # 2. 根据状态执行操作
            if state == "SUCCESS":
                self._logger.info("账号已解锁，无需操作")
                return True

            if state == "SUSPENDED":
                self._logger.error("账号已被封禁")
                return False

            if state == "NEED_START":
                self._logger.info("需要点击 Start 按钮")
                if not await self.click_start():
                    self._logger.error("点击 Start 按钮失败")
                    # 输出诊断信息
                    if network_errors:
                        self._logger.error(f"[诊断] 网络错误: {network_errors}")
                    if console_logs:
                        self._logger.error(f"[诊断] 控制台错误: {console_logs[-10:]}")
                    return False

                # 重新检测状态
                await asyncio.sleep(2)
                state = await self.detect_state()

            if state in ["CAPTCHA_PRESENT", "ON_ACCESS_PAGE"]:
                self._logger.info("等待验证码处理...")
                if not await self.wait_for_captcha():
                    self._logger.error("验证码处理超时")
                    # 尝试刷新页面并重新检测
                    self._logger.info("尝试刷新页面...")
                    await page.reload(wait_until="networkidle")
                    await asyncio.sleep(2)
                    state = await self.detect_state()
                    if state not in ["SUCCESS", "NEED_CONTINUE"]:
                        return False

                # 重新检测状态
                await asyncio.sleep(2)
                state = await self.detect_state()

            if state == "NEED_CONTINUE":
                self._logger.info("需要点击 Continue 按钮")
                await self.click_continue()

                # 重新检测状态
                await asyncio.sleep(2)
                state = await self.detect_state()

            # 如果仍然在 access 页面但没有按钮，尝试导航到首页
            if state == "ON_ACCESS_PAGE":
                self._logger.info("尝试直接导航到首页...")
                await page.goto("https://x.com/home", wait_until="networkidle")
                await asyncio.sleep(3)
                state = await self.detect_state()

            # 3. 验证结果
            if await self.verify_success():
                self._logger.info("🎉 解锁成功！")
                return True
            else:
                # 最后检查 URL
                current_url = self.browser.page.url
                if "/home" in current_url:
                    self._logger.info("🎉 解锁成功（通过 URL 确认）！")
                    return True

                self._logger.warning(f"无法确认解锁状态，当前 URL: {current_url}")

                # 输出诊断摘要
                if network_errors:
                    self._logger.warning(f"[诊断] 捕获到 {len(network_errors)} 个网络错误")
                if console_logs:
                    self._logger.warning(f"[诊断] 捕获到 {len(console_logs)} 条控制台错误/警告")

                return False

        finally:
            # 清理监听器
            page.remove_listener("console", on_console)
            page.remove_listener("response", on_response)


async def inject_stealth_script(page) -> bool:
    """
    注入隐身脚本到页面

    在页面导航前注入，消除 Playwright/CDP 指纹特征

    Args:
        page: Playwright 页面对象

    Returns:
        是否注入成功
    """
    try:
        # 使用 add_init_script 确保在每个新页面加载时都注入
        await page.context.add_init_script(STEALTH_JS)
        logger.info("[Stealth] 隐身脚本已注入到 context")

        # 在当前页面立即执行一次
        await page.evaluate(STEALTH_JS)
        logger.info("[Stealth] 隐身脚本已在当前页面执行")

        return True
    except Exception as e:
        logger.warning(f"[Stealth] 注入隐身脚本失败: {e}")
        return False


async def ensure_unlock_page(provider: BitBrowserProvider) -> None:
    """切换到解锁页（优先复用已有 x.com 页面）"""
    try:
        context = provider.context
    except Exception as e:
        logger.warning(f"无法获取浏览器上下文: {e}")
        return

    pages = list(context.pages)
    target = None

    for page in pages:
        url = page.url or ""
        if "/account/access" in url:
            target = page
            break

    if not target:
        for page in pages:
            url = page.url or ""
            if "x.com" in url:
                target = page
                break

    if not target:
        target = await context.new_page()

    if "/account/access" not in (target.url or ""):
        await target.goto("https://x.com/account/access", wait_until="domcontentloaded")
        await asyncio.sleep(1)

    try:
        await target.bring_to_front()
    except Exception:
        pass

    provider._page = target
    logger.info(f"已切换到解锁页: {target.url}")


async def main(browser_id: str, keep_open: bool = True) -> int:
    """主函数"""
    setup_main_logger()

    logger.info("=" * 50)
    logger.info("Twitter 解锁调试工具")
    logger.info("=" * 50)
    logger.info(f"浏览器 ID: {browser_id}")
    logger.info(f"保持窗口打开: {keep_open}")
    logger.info("=" * 50)

    provider = None

    try:
        # 1. 连接到现有浏览器
        logger.info("连接到比特浏览器窗口...")
        provider = BitBrowserProvider(reuse_browser_id=browser_id)
        await provider.start()
        logger.info("连接成功！")

        # 2. 写入插件配置（如启用插件模式）
        config = None
        try:
            config_path = project_root / "config.yaml"
            config = load_config(config_path=config_path if config_path.exists() else None)
        except Exception as e:
            logger.warning(f"加载配置失败，跳过插件配置: {e}")

        if config:
            await apply_captcha_plugin_config(provider, config)

        # 3. 切换到解锁页并注入隐身脚本（消除 Playwright 指纹）
        await ensure_unlock_page(provider)
        await inject_stealth_script(provider.page)

        # 3. 创建调试器并运行
        debugger = UnlockDebugger(provider)
        success = await debugger.run()

        # 3. 保存 Cookies（如果成功）
        if success:
            output_dir = project_root / "output" / "cookies"
            output_dir.mkdir(parents=True, exist_ok=True)

            # 尝试从页面获取用户名
            try:
                page = provider.page
                # 从 URL 或页面内容获取用户名
                account_id = "debug_account"
                await debugger.save_cookies(account_id, output_dir)
            except Exception as e:
                logger.warning(f"保存 Cookies 失败: {e}")

        return 0 if success else 1

    except Exception as e:
        logger.error(f"执行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        if provider and not keep_open:
            logger.info("关闭浏览器连接...")
            await provider.close()
        elif provider:
            # 只断开 Playwright 连接，保持浏览器窗口打开
            logger.info("断开连接（浏览器窗口保持打开）")
            if provider._browser:
                try:
                    await provider._browser.close()
                except Exception:
                    pass
            if provider._playwright:
                try:
                    await provider._playwright.stop()
                except Exception:
                    pass


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Twitter 解锁调试工具 - 连接到现有浏览器窗口继续流程"
    )

    parser.add_argument(
        "--browser-id", "-b",
        required=True,
        help="比特浏览器窗口 ID"
    )

    parser.add_argument(
        "--close",
        action="store_true",
        help="执行完成后关闭浏览器窗口（默认保持打开）"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试日志"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.debug:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    exit_code = asyncio.run(main(
        browser_id=args.browser_id,
        keep_open=not args.close
    ))
    sys.exit(exit_code)
