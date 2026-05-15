---
name: codexzh-token-email-reminder
description: Set up, start, stop, pause, resume, update, debug, or document a scheduled CodexZH token usage reminder that queries today's CodexZH API usage, estimates token consumption, logs snapshots, and sends styled HTML email reports through an email-mcp configured mailbox such as QQ Mail. Use when the user asks to enable/disable CodexZH token usage email reminders, pause the timer before leaving work, resume alerts, configure periodic quota emails, manage the LaunchAgent schedule, change the working-hours/off-hours cadence, or improve the reminder email template including prominent today/week spend cards.
---

# CodexZH Token Email Reminder

## Overview

Use this skill to maintain the local workflow that sends CodexZH token usage reports by email on a schedule. The expected macOS setup is:

- CodexZH usage query script: `~/.codex/skills/codexzh-api-usage/scripts/query_codexzh_usage.py`
- email-mcp encrypted credentials: `~/.email-mcp/credentials.enc`
- runnable reminder scripts: `~/.codex/scripts/codexzh_usage_snapshot.py` and `~/.codex/scripts/send_email_via_email_mcp.mjs`
- LaunchAgent: `~/Library/LaunchAgents/com.codexzh.usage-monitor.plist`
- logs: `~/.codex/log/codexzh-usage-*.log`

Never store a mail password or authorization code in the reminder scripts. Reuse email-mcp encrypted credentials and select accounts by email address or account id.

## Bundled Scripts

- `scripts/codexzh_usage_snapshot.py`: query CodexZH usage JSON, estimate token usage at `500,000 tokens / $1`, append text and JSONL logs, and send a styled HTML email with prominent today/week spend cards.
- `scripts/send_email_via_email_mcp.mjs`: decrypt local email-mcp credentials at runtime and send through SMTP using `nodemailer`.
- `scripts/start_usage_monitor.sh`: validate the LaunchAgent plist and load `com.codexzh.usage-monitor` into the current user's launchd domain.
- `scripts/stop_usage_monitor.sh`: unload `com.codexzh.usage-monitor` from the current user's launchd domain without deleting scripts, logs, or plist.

The snapshot script supports these environment overrides:

```text
CODEXZH_USAGE_QUERY_SCRIPT
CODEXZH_NODE_BIN
CODEXZH_SEND_EMAIL_SCRIPT
CODEXZH_EMAIL_ACCOUNT
CODEXZH_EMAIL_TO
CODEXZH_USAGE_LOG_DIR
```

Email subjects should use the readable timestamp format:

```text
CodexZH 用量更新 · 已用 61.2% · 2026年04月27日 17时03分10秒
```

Use the same formatted timestamp in the HTML header instead of an ISO timestamp.

## Reminder Rules

- Default reminder cadence is hourly on the hour for the full day, plus extra `:30` checks from `09:30` through `17:30`. That yields 30-minute checks during `09:00` through `18:00` work hours and hourly checks otherwise.
- The email's first visible content block should include two high-contrast spend cards labeled `今日消费` and `本周消费`.
- The secondary metric card area should show `周额度`; do not render `今日已用`, `今日剩余`, or `当前 TPM` as cards.
- Keep money metrics prominent and token/call/rate metrics secondary. The spend cards should show USD amounts plus token estimates derived from `500,000 tokens / $1`.
- Include both today and week spend in the hidden preheader and text log line so compact mail previews and logs expose the same headline information.
- Persist `weekTokensUsedEstimate` in the JSONL snapshot whenever `weekUsedUsd` is available.
- Before sending an email, compare the current `totalUsedUsd` with the most recent JSONL snapshot where `emailSent` is not `false`. If the total is unchanged, append the snapshot with `emailSent: false` and `emailSkippedReason: "total usage unchanged"`, then skip sending.

## Setup Workflow

1. Verify CodexZH usage querying works:

```zsh
~/.codex/skills/codexzh-api-usage/scripts/query_codexzh_usage.py --json
```

2. Verify the email-mcp account can connect. Prefer the MCP tool `email_test_account` when available. For QQ Mail, the configured account should include SMTP metadata like `smtp.qq.com:465`.

3. Install or refresh the scripts from this skill:

```zsh
mkdir -p ~/.codex/scripts ~/.codex/log
cp ~/.codex/skills/codexzh-token-email-reminder/scripts/codexzh_usage_snapshot.py ~/.codex/scripts/codexzh_usage_snapshot.py
cp ~/.codex/skills/codexzh-token-email-reminder/scripts/send_email_via_email_mcp.mjs ~/.codex/scripts/send_email_via_email_mcp.mjs
chmod 755 ~/.codex/scripts/codexzh_usage_snapshot.py ~/.codex/scripts/send_email_via_email_mcp.mjs
```

4. Create or update `~/Library/LaunchAgents/com.codexzh.usage-monitor.plist`. Use `StartCalendarInterval` entries for hourly `:00` checks across the full day plus `:30` checks from `09:30` through `17:30`. Add `EnvironmentVariables` if the recipient or sender account differs from the default.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.codexzh.usage-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/renshuaiweidemac/.codex/scripts/codexzh_usage_snapshot.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/renshuaiweidemac</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CODEXZH_EMAIL_ACCOUNT</key>
        <string>1982549567@qq.com</string>
        <key>CODEXZH_EMAIL_TO</key>
        <string>1982549567@qq.com</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/renshuaiweidemac/.codex/log/codexzh-usage-monitor.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/renshuaiweidemac/.codex/log/codexzh-usage-monitor.err.log</string>
</dict>
</plist>
```

5. Validate and load:

```zsh
plutil -lint ~/Library/LaunchAgents/com.codexzh.usage-monitor.plist
/usr/bin/python3 ~/.codex/scripts/codexzh_usage_snapshot.py
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.codexzh.usage-monitor.plist
launchctl print gui/$(id -u)/com.codexzh.usage-monitor
```

Running the snapshot script manually sends a real email. Use `--force-email` for a deliberate test email even when total usage is unchanged, and tell the user before doing this if they did not explicitly request a test email.

## Start and Stop Workflow

Use these commands for the live reminder after the setup exists.

To pause or disable reminder emails:

```zsh
~/.codex/skills/codexzh-token-email-reminder/scripts/stop_usage_monitor.sh
launchctl print gui/$(id -u)/com.codexzh.usage-monitor
```

The expected verification result after stopping is `Could not find service "com.codexzh.usage-monitor"`. Stopping only unloads the LaunchAgent; it keeps the plist, scripts, credentials, and logs in place.

To enable or resume reminder emails:

```zsh
~/.codex/skills/codexzh-token-email-reminder/scripts/start_usage_monitor.sh
launchctl print gui/$(id -u)/com.codexzh.usage-monitor
```

Starting the reminder only loads the schedule. It does not send an immediate email unless you separately run:

```zsh
/usr/bin/python3 ~/.codex/scripts/codexzh_usage_snapshot.py --force-email
```

If the user says something like "开启邮件提醒 codexzh 的 token 用量", treat it as a request to run the start workflow. If the user says "暂停/关闭/下班了/先别发了", treat it as a request to run the stop workflow.

## Update Workflow

When improving the reminder:

1. Patch the installed script in `~/.codex/scripts/` if the user wants the live reminder changed.
2. Mirror reusable improvements back into this skill's `scripts/` directory.
3. Run syntax checks:

```zsh
python3 -c "import ast,pathlib; ast.parse(pathlib.Path('/Users/renshuaiweidemac/.codex/scripts/codexzh_usage_snapshot.py').read_text(encoding='utf-8'))"
node --check /Users/renshuaiweidemac/.codex/scripts/send_email_via_email_mcp.mjs
```

4. For schedule changes, unload and reload the LaunchAgent if needed:

```zsh
launchctl bootout gui/$(id -u)/com.codexzh.usage-monitor
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.codexzh.usage-monitor.plist
```

## Troubleshooting

- `Operation not permitted`: rerun the same filesystem or launchctl command with explicit user approval for escalated permissions.
- `nodemailer not found`: run or reinstall `npx @marlinjai/email-mcp`, then verify `~/.npm/_npx/.../node_modules/nodemailer` exists.
- SMTP/auth failures: test the email-mcp account first; do not ask for or save plaintext passwords unless the user is intentionally reconfiguring email-mcp.
- CodexZH network errors such as incomplete reads can be transient. Check `~/.codex/log/codexzh-usage-monitor.err.log`, then rerun the snapshot once.
- If launchctl says the service already exists, use `launchctl bootout gui/$(id -u)/com.codexzh.usage-monitor` before bootstrapping again.
