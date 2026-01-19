# Product Context

> 产品需求上下文 - 需求变更时更新

---

## 产品定位

**产品名称**: Twitter Auto Unlocker 2.0

**产品形态**: CLI 工具 / 自动化脚本

**核心目标**: 批量自动解锁被限制的 Twitter 账号

**核心用户**: 需要批量管理 Twitter 账号的运营人员

---

## MVP 范围（必须做）

| 功能 | 状态 | 说明 |
|------|------|------|
| 批量账号解锁 | ✅ | 支持并发 3-10 个浏览器 |
| Cloudflare Turnstile 验证 | ✅ | YesCaptcha 人机助手自动处理 |
| Arkose FunCaptcha 验证 | ✅ | YesCaptcha 人机助手自动处理 |
| 自动登录 + TOTP 2FA | ✅ | 支持 TOTP 验证码自动生成 |
| 解锁后导出 cookies | ✅ | JSON 格式保存 |

---

## 非目标（MVP 不做）

- API 集成模式（V2 功能）
- 图形界面
- 账号注册功能

---

## 质量约束（硬约束）

| 约束 | 说明 |
|------|------|
| 必须使用 SOCKS5 代理 | 运行环境无法直连 Twitter |
| 独立浏览器指纹 | 每个浏览器实例必须有独立指纹 |
| 浏览器类型 | 使用 BitBrowser（通过 API 管理） |
| 验证码处理 | YesCaptcha 人机助手插件（推荐） |

---

## 数据边界

| 类型 | 来源/存储 |
|------|-----------|
| 账号数据 | 本地文件（`accounts.txt`） |
| 会话数据 | 本地文件（`cookies.json`） |
| 配置数据 | 本地文件（`config.yaml`） |

---

## 最后更新

- **时间**: 2026-01-19
- **操作**: 创建初始 productContext.md
