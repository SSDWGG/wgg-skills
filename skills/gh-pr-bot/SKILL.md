---
name: gh-pr-bot
description: 自动扫描 GitHub 上 ~500 star 的 JS/TS 项目，发现 good-first-issue，自动生成修复并提交 PR，追踪审批状态。触发场景：用户说"扫描 GitHub 项目""自动提 PR""查看 PR 审批进度""继续提 PR"等。
---

# GitHub PR Bot — 自动扫描、提交、追踪

## 概述

自动扫描 GitHub 上 400-700 star 的 TypeScript/JavaScript 项目，发现标记为 "good first issue" 的简单 issue，生成修复并提交 PR，最后持续追踪审批进度和合并状态。

完整链路：**发现仓库 → 扫描 issue → 分析可修复性 → 生成修复 → 提交 PR → 追踪状态 → 保存报告**

## 工作流程

### 1. 扫描 (scan)

```
python py/gh_pr_bot/main.py scan --stars 400..700 --language typescript
```

- 使用 GitHub Search API 搜索 stars 范围内的 TS/JS 仓库
- 要求 `good-first-issues:>0` 且最近有推送
- 对每个候选仓库，获取 "good first issue" / "help wanted" 标签的 open issue
- 用规则评分系统过滤出可修复的 issue
- 结果保存到 `~/.codex/monitoring/gh-pr-bot/candidates.json`

### 2. 提交 (submit)

```
python py/gh_pr_bot/main.py submit [--issue-url URL]
```

- 从候选列表中选择最佳 issue（或指定 URL）
- Fork 仓库，clone 代码
- 根据 fix_type 生成修复：
  - `typo` — 拼写检查 + 替换
  - `documentation` — 补充文档内容
  - `simple_bug` — 简单代码修复
- Commit + Push + 创建 PR
- 状态写入 `~/.codex/monitoring/gh-pr-bot/prs.json`

### 3. 状态追踪 (status)

```
python py/gh_pr_bot/main.py status
```

- 检查所有已提交 PR 的状态（OPEN / MERGED / CLOSED）
- 显示 reviewer 评论数和审查状态
- 标记需要签 CLA 的 PR
- 更新结果到 `~/.codex/monitoring/gh-pr-bot/prs.json`

### 4. 自动模式 (auto)

```
python py/gh_pr_bot/main.py auto
```

- 执行 scan → 选最佳 → submit → save 的完整流程
- 每次只提交 1 个 PR，避免 API 限流

## 配置

在 `.env` 文件中配置：

```bash
# GitHub token（或使用 gh auth token）
GH_TOKEN=ghp_xxx

# Output directory
BOT_OUTPUT_DIR=~/.codex/monitoring/gh-pr-bot

# PR limits
BOT_MAX_PRS_PER_RUN=1
BOT_MAX_PRS_PER_REPO=1

# Star range
BOT_MIN_STARS=400
BOT_MAX_STARS=700
```

## 输出文件

| 文件 | 内容 |
|------|------|
| `candidates.json` | 扫描发现的候选 issue |
| `prs.json` | 已提交 PR 及其状态 |
| `runs.jsonl` | 每次运行的日志 |
| `scanned_repos.json` | 已扫描过的仓库列表 |

## 修复类型

| Fix Type | 描述 | 示例 |
|----------|------|------|
| `typo` | 拼写错误 | "recieve" → "receive" |
| `documentation` | 补充文档 | 填充 TBD 章节、添加配置说明 |
| `broken_link` | 修复死链 | 更新重定向的 URL |
| `simple_bug` | 简单 bug | 单行代码修复、路由重定向 |
| `i18n` | 国际化修复 | 翻译标签修正 |

## 安全措施

- **只能修复明确标记 "good first issue" 的 issue**
- 不提交涉及安全、性能、架构的修复
- 每仓库最多 1 个 PR，每次运行最多 1-3 个 PR
- Fork 前检查是否已有 open PR 处理同一 issue
- 修复前确认 issue 仍然 open 且未被 assign
