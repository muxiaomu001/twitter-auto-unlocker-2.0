# Tech Context

> 技术决策上下文 - 架构/依赖/接口变更时更新

---

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.10+ |
| 异步框架 | asyncio | 内置 |
| 浏览器自动化 | Playwright | >=1.40.0 |
| HTTP 客户端 | aiohttp | >=3.9.0 |
| 2FA 生成 | pyotp | >=2.9.0 |
| 文件操作 | aiofiles | >=23.2.1 |
| 配置解析 | pyyaml | >=6.0.1 |

---

## 架构决策

### 1. 浏览器选择

| 决策 | 使用 BitBrowser |
|------|----------------|
| **原因** | 支持指纹管理、API 控制、多实例并发 |
| **替代方案** | Camoufox（已废弃） |
| **影响面** | `core/bitbrowser_provider.py`, `core/bitbrowser_client.py` |

### 2. 验证码处理

| 决策 | YesCaptcha 人机助手插件 |
|------|------------------------|
| **原因** | 自动处理所有验证码类型，无需代码干预 |
| **替代方案** | YesCaptcha API 图像识别（备用） |
| **影响面** | `core/unlock_flow.py` |

### 3. 并发模型

| 决策 | asyncio + 信号量控制 |
|------|---------------------|
| **原因** | 轻量级、高效、易于控制并发数 |
| **影响面** | `queue/worker.py` |

---

## 模块依赖关系

```
main.py
    └── queue/worker.py
            ├── core/unlock_flow.py
            │       ├── core/bitbrowser_provider.py
            │       ├── account/auth.py
            │       └── core/session.py
            └── account/parser.py
```

---

## API 接口

### BitBrowser API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/browser/open` | POST | 打开浏览器实例 |
| `/browser/close` | POST | 关闭浏览器实例 |
| `/browser/list` | GET | 列出浏览器实例 |

**默认地址**: `http://127.0.0.1:54345`

---

## 最后更新

- **时间**: 2026-01-19
- **操作**: 创建初始 techContext.md
