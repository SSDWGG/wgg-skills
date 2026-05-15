---
name: hermes-weixin-gateway
description: Connect, operate, verify, and troubleshoot Hermes Agent's Weixin / personal WeChat IM gateway. Use when the user asks to connect Hermes to 微信/WeChat/Weixin, scan the iLink QR login, start or restart the Hermes gateway, approve Weixin pairing, verify inbound replies, inspect why Hermes is not responding in Weixin, or compare Hermes Weixin with chatgpt-on-wechat.
---

# Hermes Weixin Gateway

## Scope

Use Hermes as the preferred local Weixin IM bridge. Hermes already has a native `weixin` adapter backed by Tencent iLink Bot API; do not reimplement a WeChat client or switch to `chatgpt-on-wechat` unless the user asks for that fallback.

Do not expose `WEIXIN_TOKEN`, `WEIXIN_ACCOUNT_ID`, model API keys, or `.env` secrets in chat. Redact secret values in command output.

## Quick Workflow

1. Check local state:

```zsh
hermes gateway status
test -f ~/.hermes/.env && grep -E '^(WEIXIN_ACCOUNT_ID|WEIXIN_BASE_URL|WEIXIN_CDN_BASE_URL|WEIXIN_DM_POLICY|WEIXIN_GROUP_POLICY)=' ~/.hermes/.env
find ~/.hermes/weixin/accounts -maxdepth 1 -type f 2>/dev/null
```

2. If Weixin credentials are absent or stale, run the interactive setup:

```zsh
hermes gateway setup
```

Select `Weixin / WeChat`, start QR login, and have the user scan and confirm in WeChat. Use foreground/TTY execution so the QR code is visible. Tell the user before starting that this requires their phone scan.

3. Prefer secure access choices during setup:

- Direct messages: `Use DM pairing approval`
- Group chats: `Disable group chats`
- Home channel: accept only if the user wants proactive sends to their own Weixin user ID

4. Start or restart the gateway:

```zsh
hermes gateway start
hermes gateway status
```

If no service is installed, use:

```zsh
hermes gateway run
```

Run foreground mode only while actively testing; otherwise install/start the service through Hermes.

5. Verify response flow:

- Ask the user to send a Weixin DM to the connected account.
- If Hermes returns a pairing code, approve it:

```zsh
hermes pairing approve weixin <code>
```

- Ask the user to send another message after approval.
- Check:

```zsh
hermes logs gateway -n 120
hermes logs errors -n 120
cat ~/.hermes/channel_directory.json
```

## How Hermes Weixin Works

- QR login obtains an iLink `account_id`, `bot_token`, base URL, and user ID.
- Setup saves env values in `~/.hermes/.env` and account credentials in `~/.hermes/weixin/accounts/<account_id>.json`.
- Gateway config maps `WEIXIN_TOKEN` and `WEIXIN_ACCOUNT_ID` into the `Platform.WEIXIN` adapter.
- The adapter long-polls iLink `getupdates`, deduplicates inbound messages, stores per-peer `context_token`, downloads inbound media, then calls the shared gateway message handler.
- Replies use iLink `sendmessage`. Text is Markdown-normalized and split under Weixin limits; files/images/video are AES-encrypted, uploaded to Weixin CDN, then sent as media items.
- Weixin does not support editing sent messages, so do not expect streaming edits.

Read `references/source-map.md` when you need exact local source paths, functions, or deeper troubleshooting.

## Troubleshooting

- `Gateway is not running`: run `hermes gateway start` or `hermes gateway run`.
- Missing dependency errors: Weixin requires `aiohttp` and `cryptography` in the Hermes runtime.
- `WEIXIN_TOKEN is required` or `WEIXIN_ACCOUNT_ID is required`: rerun QR setup or inspect `~/.hermes/.env` and `~/.hermes/weixin/accounts/`.
- Unauthorized user: approve the pairing code with `hermes pairing approve weixin <code>`, or intentionally configure `WEIXIN_ALLOWED_USERS`.
- Group messages ignored: expected when `WEIXIN_GROUP_POLICY=disabled`.
- Session expired / `-14`: Hermes may retry without `context_token`; if replies still fail, rerun QR setup.
- No channel directory entries: Weixin directory is session-derived; it fills after inbound messages create sessions.
- TLS/cert issues reaching `ilinkai.weixin.qq.com`: Hermes attempts a certifi CA connector. Verify network/proxy before editing code.

## Safety

Ask before actions that send messages, start QR login, change access policy, or start a long-running gateway service. Never make `WEIXIN_ALLOW_ALL_USERS=true` or open group chat access unless the user explicitly asks.
