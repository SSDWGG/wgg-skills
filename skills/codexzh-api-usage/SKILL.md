---
name: "codexzh-api-usage"
description: "Query CodexZH API usage and remaining quota through `https://codexzh.com/api-usage` and `https://codexzh.com/api/v1/usage/stats`. Use when the user asks to 查询 CodexZH API 用量、剩余额度、剩余 API、日/周消费、token 额度、订阅到期时间, or to inspect a CodexZH API key."
---

# CodexZH API Usage

Query CodexZH usage with the bundled script instead of re-discovering the web flow.
Treat `remaining quota` as the daily and weekly quota minus `todayUsed` and `weekUsed`.

## Key Source

Resolve the API key in this order:

1. Explicit `--key` argument
2. `CODEXZH_API_KEY`
3. `~/.codex/codexzh-api-key`

If none exist, ask the user for the key.
Do not write the key into `SKILL.md` or echo the full key back in chat unless the user explicitly asks.

## Quick Start

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export CODEXZH_SKILL="$CODEX_HOME/skills/codexzh-api-usage"

"$CODEXZH_SKILL/scripts/query_codexzh_usage.py"
"$CODEXZH_SKILL/scripts/query_codexzh_usage.py" --json
"$CODEXZH_SKILL/scripts/query_codexzh_usage.py" --save-key "sk-..."
```

## Workflow

1. Run the script without arguments when the local key is already configured.
2. Run with `--save-key` once when the user wants future direct queries from this machine.
3. If the sandbox blocks network access, rerun with escalation instead of changing the script.
4. Report the fields the user actually cares about first:
   - daily remaining quota
   - weekly remaining quota
   - today and week spend
   - total spend
   - subscription expiry

## Output Rules

- For “查询剩余 codexzh api”, lead with remaining daily and weekly quota.
- Include both formatted USD values and raw call-rate info when available.
- If the API returns `TOKEN_EXPIRED`, state that the subscription is expired.
- If the API returns HTTP `401`, state that the key is invalid.
- When the user asks for the exact raw payload, rerun with `--json`.
