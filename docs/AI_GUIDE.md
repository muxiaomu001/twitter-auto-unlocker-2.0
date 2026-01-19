# AI Usage Guide

> AI 助手使用本项目的指南 - 关键入口点、修改模式、代码示例

---

## Key Entry Points

1. **CLI 入口**: `main.py` - 解析参数、加载配置、启动批量处理
2. **批量处理**: `x_unlocker/queue/worker.py` - 并发控制与任务调度
3. **解锁流程**: `x_unlocker/core/unlock_flow.py` - 状态机驱动的主流程
4. **登录认证**: `x_unlocker/account/auth.py` - Twitter 登录 + 2FA

---

## Common Modification Patterns

### 添加新的验证码类型

```python
# 1. Create handler in x_unlocker/captcha/new_captcha.py
class NewCaptchaHandler:
    async def detect(self) -> bool: ...
    async def solve(self) -> Tuple[bool, Optional[str]]: ...

# 2. Add to unlock_flow.py detection logic
if await new_captcha_handler.detect():
    await new_captcha_handler.solve()
```

### 修改账号解析格式

```python
# Edit x_unlocker/account/parser.py
# - Update parse_account_line() for new format
# - Update AccountInfo dataclass for new fields
```

### 添加新的登录状态处理

```python
# Edit x_unlocker/account/auth.py
# - Add to LoginResult enum
# - Add detection logic in _check_page_state()
# - Add handler method if needed
```

---

## Important State Machine (UnlockFlow)

```
INIT --> LOGGING_IN --> [风控检测]
                              |
                    +---------+---------+
                    |                   |
            UNUSUAL_ACTIVITY    ENTERING_PASSWORD
                    |                   |
                    +--------->---------+
                              |
                        VERIFYING_2FA
                              |
                    WAITING_CLOUDFLARE (插件处理)
                              |
                    WAITING_FUNCAPTCHA (插件处理)
                              |
                          VERIFYING
                              |
                    +---------+---------+
                    |                   |
                 SUCCESS             FAILED
                    |
                  SAVING
```

---

## BitBrowser Provider Usage

```python
# Context manager (recommended)
async with BitBrowserProvider(config) as provider:
    page = await provider.get_page()
    await page.goto("https://x.com")
    await page.type("#input", "text")
    await page.click("#button")

# Manual management
provider = BitBrowserProvider(config)
await provider.start()
page = await provider.get_page()
# ... use page ...
await provider.close()
```

---

## YesCaptcha 人机助手（推荐方式）

验证码由浏览器插件自动处理，代码只需等待：

```python
# unlock_flow.py 中的处理逻辑
async def _wait_for_plugin(self) -> Tuple[bool, Optional[str]]:
    """等待 YesCaptcha 插件自动处理验证码"""
    max_wait_time = self.config.captcha.plugin_max_wait_time
    start_time = time.time()

    while True:
        # 检测验证码 iframe 是否消失（插件处理完成的标志）
        captcha_iframe = await page.query_selector(
            'iframe[src*="arkoselabs"], iframe[src*="turnstile"]'
        )
        if not captcha_iframe:
            return True, None  # 处理完成

        if time.time() - start_time > max_wait_time:
            return False, "插件处理超时"

        await asyncio.sleep(1)
```

> **注意**：需要在比特浏览器中预先安装 YesCaptcha 人机助手插件并配置 API Key

---

## Related Files

| Category | Files |
|----------|-------|
| Entry | `main.py` |
| Config | `config.yaml`, `requirements.txt` |
| Data | `accounts.txt` |
| Output | `output/` directory |
| Docs | `docs/plan.md`, `docs/TECH_REFERENCE.md` |
| Context | `memory-bank/` |
