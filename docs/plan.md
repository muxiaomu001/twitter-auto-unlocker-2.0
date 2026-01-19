# 任务计划

> 任务开始前查阅，任务结束后更新

---

## 当前任务：CLAUDE.md 拆分优化

### 背景

CLAUDE.md 当前有 586 行，包含：
- 项目宪法规则（1-130 行，22%）
- 技术参考文档（133-586 行，78%）

**问题**：文件过长，规则与技术文档混杂，不便维护

### 目标

拆分为 3 个文件：
1. `CLAUDE.md` → 只保留宪法规则（~130 行）
2. `docs/TECH_REFERENCE.md` → 技术参考文档（~250 行）
3. `docs/AI_GUIDE.md` → AI 使用指南（~100 行）

---

## 实施步骤

### Step 1: 创建目录结构 ✅
- [x] 创建 `memory-bank/` 目录
- [x] 创建 `docs/` 目录

### Step 2: 初始化 Memory Bank ✅
- [x] 创建 `activeContext.md`
- [x] 创建 `productContext.md`
- [x] 创建 `techContext.md`
- [x] 创建 `progress.md`

### Step 3: 创建 docs/plan.md ✅
- [x] 创建本文件

### Step 4: 拆分 CLAUDE.md ✅
- [x] 提取技术参考到 `docs/TECH_REFERENCE.md`（336 行）
- [x] 提取 AI 指南到 `docs/AI_GUIDE.md`（136 行）
- [x] 精简 CLAUDE.md（141 行，减少 76%）
- [x] 添加文档引用指向

### Step 5: 验证 ✅
- [x] 确认文件行数符合预期
- [x] 确认目录结构完整

---

## 验收标准

1. ✅ `CLAUDE.md` 行数 ≤ 150 行（实际 141 行）
2. ✅ 所有 Memory Bank 文件存在且有内容
3. ✅ `docs/` 包含 `plan.md`、`TECH_REFERENCE.md`、`AI_GUIDE.md`

---

## 回滚策略

如需回滚，可从 Git 历史恢复原始 CLAUDE.md

---

## 最后更新

- **时间**: 2026-01-19
- **状态**: ✅ 全部完成
