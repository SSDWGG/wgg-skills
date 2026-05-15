---
name: hermes-responses-api-adapter-fix
description: Diagnose and fix local Hermes GPT-family custom-provider routing when codexzh, GPT-5.x, Codex, or OpenAI-compatible relay requests fail because they are using Chat Completions instead of the OpenAI Responses API. Use when Hermes errors mention empty input[n].name, openai-responses, codex_responses, api_mode, /v1/chat/completions, /v1/responses, custom_providers, or GPT models needing Responses API mode.
---

# Hermes Responses API Adapter Fix

Chinese alias: hermes使用responses模式api的适配修复.

## Goal

Make Hermes route GPT-family custom-provider calls through the Responses API. In Hermes config this is written as `api_mode: codex_responses`, even when user-facing docs or relay configs call the protocol `openai-responses`.

## Workflow

1. Inspect the active config before editing.
   - Read `~/.hermes/config.yaml`.
   - Identify `model.default`, `model.provider`, `model.base_url`, `model.api_mode`, and matching `custom_providers` or `providers` entries.
   - Redact `api_key`, tokens, and credential values in all user-visible output.

2. Match the failure pattern.
   - `Invalid 'input[n].name': empty string` with a GPT-family model usually means the request was sent to an OpenAI-compatible Chat Completions route.
   - GPT-family models such as `gpt-5.x`, `gpt-5.x-codex`, `codex-*`, and many CodexZH relay models should use Responses mode.
   - Missing `api_mode` in Hermes usually falls back to `chat_completions` unless runtime code auto-detects that endpoint.

3. Apply the minimal Hermes fix.
   - For the active `model:` block, set:

```yaml
model:
  api_mode: codex_responses
```

   - For a matching named custom provider, also set:

```yaml
custom_providers:
- name: codexzh
  api_mode: codex_responses
```

   - If using the newer `providers:` dict, use `transport: codex_responses` or `api_mode: codex_responses` according to the existing style.
   - Do not set Hermes `api_mode` to `openai-responses`; current Hermes validation accepts `codex_responses` as the internal name for Responses API mode.

4. Verify without exposing secrets.
   - Run `hermes config check`.
   - Run `hermes doctor` when useful; ignore unrelated optional-tool warnings.
   - Verify runtime resolution with a Python one-liner that prints only non-secret fields:

```zsh
~/.hermes/hermes-agent/venv/bin/python -c "from hermes_cli.runtime_provider import resolve_runtime_provider; r=resolve_runtime_provider(requested='custom'); print({k:r.get(k) for k in ('provider','api_mode','base_url','source','requested_provider')})"
```

   - Expected result: `api_mode` is `codex_responses`, and `base_url` is the intended relay endpoint.

5. Restart only if needed.
   - If the failing request came from a long-running gateway/service, restart it after config changes:

```zsh
hermes gateway restart
```

## Local Source Checks

Use these files when the config behavior is unclear:

- `~/.hermes/hermes-agent/hermes_cli/runtime_provider.py`: resolves `api_mode`, custom providers, and endpoint auto-detection.
- `~/.hermes/hermes-agent/hermes_cli/config.py`: normalizes `custom_providers` and `providers` entries.
- `~/.hermes/hermes-agent/hermes_cli/providers.py`: maps transport names to Hermes `api_mode` values.
- `~/.hermes/hermes-agent/tests/hermes_cli/test_runtime_provider_resolution.py`: examples for custom providers and `codex_responses` routing.

## Safety Rules

- Never print API keys or `.env` values.
- Preserve unrelated config fields and comments where practical.
- Do not rewrite provider setup broadly; this fix is usually one or two YAML fields.
- Report residual warnings separately from the fixed routing issue.
