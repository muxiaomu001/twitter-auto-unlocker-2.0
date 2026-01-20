---
name: codex-review
description: |
  自动检测代码变更并提醒进行 Codex 代码审查，确保代码与文档一致性。
  触发条件：
  - 用户执行 /review 或 /codex-review 命令
  - 用户说"审查代码"、"检查变更"、"Codex 审核"、"review changes"
  - 检测到 PRD/文档（docs/**/*.md）被修改时提醒
  - 检测到 UI 组件（**/*.tsx, **/*.vue）被修改时提醒
  - 检测到类型定义（**/types.ts, **/types/*.ts）被修改时提醒
  - 检测到配置文件（**/config.ts, **/*.config.ts）被修改时提醒
  输出：Codex 审核结果报告，包含一致性检查、问题清单和修复建议。
---

# Codex Review Skill

> 确保代码变更经过审查，保持代码与文档一致性。

---

## 0. 前置条件

### Codex MCP 服务器

本 Skill 依赖 `codexmcp` MCP 服务器来执行代码审查。这是一个**社区维护的 MCP**（非官方），需要单独安装。

**安装方式**（二选一）：

#### 方式 1：用户级配置（推荐）

```bash
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp
```

#### 方式 2：项目级配置

在项目根目录的 `.mcp.json` 中添加：

```json
{
  "mcpServers": {
    "codex": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/GuDaStudio/codexmcp.git", "codexmcp"]
    }
  }
}
```

**验证安装**：重启 Claude Code 后，检查 MCP 状态中是否显示 `codex ✓`

**项目地址**：https://github.com/GuDaStudio/codexmcp

> ⚠️ 如果 `mcp__codex__codex` 工具不可用，请先按上述步骤安装 Codex MCP。

---

## 1. 工作流程

### 1.1 自动检测模式（默认）

当检测到以下类型文件被修改时，**提醒用户**是否需要 Codex 审查：

| 文件类型 | 默认检测模式 | 说明 |
|----------|-------------|------|
| 文档 | `docs/**/*.md` | PRD、技术文档 |
| UI 组件 | `**/*.tsx`, `**/*.vue` | React/Vue 组件 |
| 类型定义 | `**/types.ts`, `**/types/*.ts` | TypeScript 类型 |
| 配置 | `**/config.ts`, `**/*.config.ts` | 配置文件 |

> **优先级**：项目级 `references/project-patterns.md` > 默认模式 [references/default-patterns.md](references/default-patterns.md)。
> 如果项目中存在 `project-patterns.md`，则完全使用项目配置，忽略默认模式。

### 1.2 检测到变更时的行为

1. **分析变更**：识别修改的文件类型（文档/UI/类型/配置）
2. **提醒用户**：
   ```
   📋 检测到以下变更：
   - [文档] docs/prd/xxx.md
   - [UI] src/components/xxx.tsx

   建议进行 Codex 审查以确保代码与文档一致。
   是否执行审查？
   ```
3. **用户确认后**：执行审查流程

### 1.3 手动触发

用户可通过以下方式手动触发：
- `/review` 或 `/codex-review` 命令
- 说"审查代码"、"Codex 审核"、"review"、"检查变更"

---

## 2. 审查流程

### 2.1 调用 Codex MCP

使用 `mcp__codex__codex` 工具执行审查：

```
PROMPT: 审查变更内容（见下方模板）
cd: 项目根目录
sandbox: "read-only"
```

### 2.2 审查提示词模板

```
请审核以下变更：

## 变更摘要
{变更描述}

## 修改的文件
{文件列表}

## 审核要点
1. 代码是否遵循项目规范
2. 文档描述是否清晰完整
3. 代码与文档是否一致（版本号、配置、功能描述）
4. 是否有潜在问题或遗漏

请返回审核结果，包含：
- 审核结论：通过/需修改
- 问题清单（如有）
- 修复建议（如有）
```

### 2.3 审查报告格式

```markdown
## Codex 审核结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 版本号一致性 | ✅/⚠️ | 文档版本 vs 代码版本 |
| 配置一致性 | ✅/⚠️ | 文档配置 vs 代码实现 |
| 功能描述完整 | ✅/⚠️ | 新增功能是否有说明 |
| 代码规范 | ✅/⚠️ | 是否符合项目规范 |

### 问题清单
- [严重度] 问题描述

### 修复建议
1. 建议内容
```

> 完整审查清单见 [references/checklist-template.md](references/checklist-template.md)。

---

## 3. 评估 Codex 意见（关键步骤）

> ⚠️ **重要**：不要简单返回 Codex 的结果，必须从工程师角度评估每条意见的合理性，然后告知用户评估结论。

### 3.1 评估原则

对 Codex 提出的每个问题，使用以下标准评估：

| 评估维度 | 采纳 | 不采纳 |
|----------|------|--------|
| 一致性问题 | ✅ 文档/代码不一致 | - |
| 文档完整性 | ✅ 缺少必要说明 | - |
| 冗余信息 | - | ❌ Claude Code 已具备的能力 |
| 过度约束 | - | ❌ 限制了合理的灵活性 |
| 项目适配 | ✅ 适用于当前项目 | ❌ 仅适用于特定场景 |

### 3.2 评估流程

1. **逐条分析**：对 Codex 的每个问题独立评估（参考 3.1 评估原则表格）
2. **给出结论**：✅ 采纳 / ⚠️ 部分采纳 / ❌ 不采纳
3. **说明理由**：简要解释为什么采纳或不采纳
4. **执行修复**：仅对采纳的问题进行修复
5. **告知用户**：输出评估结果，让用户了解决策过程

### 3.3 输出格式

```markdown
## Codex 意见评估

| # | 问题 | 决定 | 理由 |
|---|------|------|------|
| 1 | [问题描述] | ✅ 采纳 | [简要理由] |
| 2 | [问题描述] | ⚠️ 部分采纳 | [简要理由] |
| 3 | [问题描述] | ❌ 不采纳 | [简要理由] |

### 已执行的修复
1. [修复内容]

### 不采纳的理由
- 问题 3：[详细说明]
```

### 3.4 常见不采纳场景

以下类型的建议通常不需要采纳：

- **冗余说明**：Claude Code 本身具备的能力（如 git status/diff）
- **过度锁定**：社区项目的版本锁定（限制了更新灵活性）
- **场景特定**：仅适用于特定项目的建议
- **增加复杂度**：为边缘情况增加过多逻辑

---

## 4. 项目定制

### 4.1 自定义检测模式

在项目中创建 `references/project-patterns.md` 覆盖默认模式：

```markdown
# 项目检测模式

## 文档文件
- docs/prd/*.md
- docs/api/*.md

## UI 组件
- src/features/*/components/*.tsx
- src/features/*/pages/*.tsx

## 类型定义
- src/features/*/types.ts

## 版本号位置
- 代码: COLUMN_CONFIG_VERSION (组件文件)
- 文档: 变更记录表格 (PRD 文件)
```

### 4.2 自定义审查清单

在项目中创建 `references/project-checklist.md` 添加项目特定检查项：

```markdown
# 项目审查清单

## 必检项
- [ ] 版本号是否同步更新
- [ ] 列配置是否与 DEFAULT_COLUMNS 一致
- [ ] 新功能是否有 PRD 说明

## 可选项
- [ ] 是否需要更新 CHANGELOG
- [ ] 是否影响其他模块
```

---

## 5. 审查结果处理

### 5.1 审查通过
- 告知用户审查结论
- 无需后续操作

### 5.2 审查不通过
1. 展示问题清单和修复建议
2. 询问用户是否需要修复
3. 用户修复后可再次触发审查
4. 循环直到通过

---

## 6. 使用示例

### 手动审查
```
用户: /review
助手: 开始 Codex 审查...
      [调用 mcp__codex__codex]
      审查完成，结果如下：
      ...
```

### 自动检测提醒
```
[用户修改了 docs/prd/xxx.md 和 src/components/xxx.tsx]

助手: 📋 检测到以下变更：
      - [文档] docs/prd/xxx.md
      - [UI] src/components/xxx.tsx

      建议进行 Codex 审查以确保代码与文档一致。
      是否执行审查？

用户: 是

助手: [执行审查流程...]
```
