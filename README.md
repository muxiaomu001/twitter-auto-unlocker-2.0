# Twitter Auto Unlocker 2.0

批量解锁被锁定的 Twitter/X 账号。

## 特性

- **BitBrowser 指纹浏览器**：通过 API 自动创建和管理浏览器实例
- **YesCaptcha 人机助手**：浏览器插件自动处理所有验证码（Cloudflare + FunCaptcha）
- **并发处理**：支持多账号并行解锁
- **状态机驱动**：可靠的解锁流程控制
- **自动重试**：失败自动重试，支持指数退避

## 解锁流程

```
登录页 → 输入账号 → [风控检测] → 输入密码 → 2FA验证
                         ↓
                    身份验证(可选)
                         ↓
              → Cloudflare验证(插件处理) → FunCaptcha验证(插件处理) → 完成解锁
```

## 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

## 前置要求

### 1. 比特浏览器

必须先启动比特浏览器客户端（默认 API 地址：`http://127.0.0.1:54345`）

### 2. YesCaptcha 人机助手插件（关键）

**安装步骤：**

1. 打开比特浏览器 → 扩展中心 → 添加自定义扩展
2. 输入 Chrome 商店 URL：
   ```
   https://chromewebstore.google.com/detail/yescaptcha-assistant/jiofmdifioeejeilfkpegipdjiopiekl
   ```
3. 安装后点击插件图标，配置 API Key
4. 启用自动识别

> **重要**：插件会自动处理 Cloudflare Turnstile 和 Arkose FunCaptcha，代码只需等待处理完成

### 3. 代理

推荐使用 SOCKS5 代理（运行环境无法直连 Twitter）

## 配置

### 1. 配置文件

编辑 `config.yaml`：

```yaml
captcha:
  # YesCaptcha API Key（人机助手插件需要）
  api_key: "YOUR_YESCAPTCHA_API_KEY"

  plugin:
    max_wait_time: 120  # 插件处理超时时间（秒）

browser:
  api_url: "http://127.0.0.1:54345"
  page_timeout: 60

concurrency:
  max_browsers: 5
```

### 2. 账号文件

创建 `accounts.txt`，格式：

```
用户名:密码:2FA密钥:代理IP
```

代理格式：`ip:端口:用户名:密码` (SOCKS5)

示例：
```
user1:password1:TOTP_SECRET1:127.0.0.1:1080:proxyuser:proxypass
user2:password2:TOTP_SECRET2:
```

## 使用

```bash
# 基本用法
python main.py --input accounts.txt

# 指定配置文件
python main.py --input accounts.txt --config config.yaml

# 命令行覆盖配置
python main.py --input accounts.txt --api-key YOUR_KEY --concurrency 10

# 调试模式
python main.py --input accounts.txt --debug
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input, -i` | 账号文件路径 | 必需 |
| `--config, -c` | 配置文件路径 | config.yaml |
| `--api-key` | YesCaptcha API Key | - |
| `--output, -o` | 输出目录 | ./output |
| `--concurrency` | 并发浏览器数 | 5 |
| `--max-attempts` | 最大重试次数 | 3 |
| `--debug` | 开启调试日志 | false |

## 输出

- `output/summary.txt` - 结果汇总
- `output/success.txt` - 成功账号列表
- `output/failed.txt` - 失败账号列表
- `output/screenshots/` - 过程截图
- `output/cookies/` - 账号 Cookies

## 项目结构

```
twitter-auto-unlocker2.0/
├── main.py                 # CLI 入口
├── config.yaml             # 配置文件
├── accounts.txt            # 账号列表
├── requirements.txt        # 依赖
├── CLAUDE.md               # 项目宪法（精简版）
├── README.md               # 本文件
├── docs/                   # 文档目录
│   ├── plan.md             # 任务计划
│   ├── TECH_REFERENCE.md   # 技术参考
│   └── AI_GUIDE.md         # AI 使用指南
├── memory-bank/            # 上下文记忆
│   ├── activeContext.md    # 当前任务状态
│   ├── productContext.md   # 产品需求
│   ├── techContext.md      # 技术决策
│   └── progress.md         # 进度记录
├── x_unlocker/             # 源代码
│   ├── account/            # 账号：解析 + 登录
│   ├── captcha/            # 验证码：配置工厂
│   ├── core/               # 核心：浏览器 + 解锁流程
│   ├── proxy/              # 代理处理
│   ├── queue/              # 并发队列
│   └── utils/              # 工具函数
└── output/                 # 输出目录
```

## 技术栈

- Python 3.10+
- Playwright (CDP 连接)
- aiohttp (异步 HTTP)
- BitBrowser API
- YesCaptcha 人机助手插件

## 版本

2.0 - 重构版本

- 仅支持 BitBrowser（移除 Camoufox）
- 仅支持 YesCaptcha 人机助手插件
- Cloudflare + FunCaptcha 统一由插件自动处理
- 简化配置和代码结构
