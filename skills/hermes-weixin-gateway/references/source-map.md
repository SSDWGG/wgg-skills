# Hermes Weixin Source Map

Use this reference only when the main skill workflow is not enough.

## Primary Local Sources

- `~/.hermes/hermes-agent/gateway/platforms/weixin.py`
  - `qr_login(...)`: fetches iLink QR code, polls status, saves credentials.
  - `save_weixin_account(...)` / `load_weixin_account(...)`: persists `~/.hermes/weixin/accounts/<account_id>.json`.
  - `WeixinAdapter.__init__`: resolves `WEIXIN_ACCOUNT_ID`, `WEIXIN_TOKEN`, base URLs, access policy, chunking behavior.
  - `WeixinAdapter.connect`: requires `aiohttp`, `cryptography`, token, and account ID; starts long polling.
  - `_poll_loop`: calls iLink `getupdates`, saves sync buffer, dispatches inbound messages.
  - `_process_message`: ignores self messages, deduplicates, applies DM/group prefilter, stores `context_token`, downloads media, builds `MessageEvent`.
  - `send`: sends text/media replies; text goes through `_send_text_chunk`.
  - `_send_file`: encrypts media, uploads to Weixin CDN, sends media item through iLink.
  - `send_weixin_direct`: one-shot helper for outbound sends and cron delivery.

- `~/.hermes/hermes-agent/hermes_cli/gateway.py`
  - `_setup_weixin`: CLI QR setup wizard, saves `WEIXIN_*` values into `~/.hermes/.env`.
  - `gateway_setup`: platform picker that routes `Weixin / WeChat` to `_setup_weixin`.
  - Gateway lifecycle commands live in the same module: `run`, `start`, `stop`, `restart`, `status`, `install`.

- `~/.hermes/hermes-agent/gateway/config.py`
  - `Platform.WEIXIN`: supported gateway platform enum.
  - `_apply_env_overrides`: maps `WEIXIN_TOKEN`, `WEIXIN_ACCOUNT_ID`, `WEIXIN_BASE_URL`, `WEIXIN_CDN_BASE_URL`, `WEIXIN_DM_POLICY`, `WEIXIN_ALLOWED_USERS`, `WEIXIN_GROUP_POLICY`, and related env vars into `PlatformConfig`.
  - `get_connected_platforms`: Weixin is considered connected only when `account_id` and token are present.

- `~/.hermes/hermes-agent/gateway/run.py`
  - `_create_adapter`: instantiates `WeixinAdapter` for `Platform.WEIXIN`.
  - `_is_user_authorized`: applies allow-all, allowlists, approved pairing users, and global auth defaults.
  - `_get_unauthorized_dm_behavior`: defaults to pairing when no allowlist is configured.
  - `_handle_message`: sends pairing codes to unauthorized DM users and runs the agent for authorized users.

- `~/.hermes/hermes-agent/gateway/pairing.py`
  - Stores pending and approved pairing data under `~/.hermes/pairing/`.
  - Codes are 8 characters, expire after 1 hour, and are rate-limited.

- `~/.hermes/hermes-agent/hermes_logging.py`
  - Logs are under `~/.hermes/logs/`.
  - `gateway.log` is created in gateway mode.
  - Use `hermes logs gateway -n 120` and `hermes logs errors -n 120`.

## Configuration Keys

`~/.hermes/.env` keys used by Weixin:

```text
WEIXIN_ACCOUNT_ID
WEIXIN_TOKEN
WEIXIN_BASE_URL
WEIXIN_CDN_BASE_URL
WEIXIN_DM_POLICY
WEIXIN_ALLOW_ALL_USERS
WEIXIN_ALLOWED_USERS
WEIXIN_GROUP_POLICY
WEIXIN_GROUP_ALLOWED_USERS
WEIXIN_HOME_CHANNEL
WEIXIN_SPLIT_MULTILINE_MESSAGES
WEIXIN_SEND_CHUNK_DELAY_SECONDS
WEIXIN_SEND_CHUNK_RETRIES
WEIXIN_SEND_CHUNK_RETRY_DELAY_SECONDS
```

Safe defaults:

```text
WEIXIN_DM_POLICY=pairing
WEIXIN_ALLOW_ALL_USERS=false
WEIXIN_ALLOWED_USERS=
WEIXIN_GROUP_POLICY=disabled
WEIXIN_GROUP_ALLOWED_USERS=
```

## Operational Notes

- `WEIXIN_DM_POLICY=pairing` relies on gateway authorization. The adapter lets non-disabled/non-allowlist DMs reach the shared handler; the handler rejects unauthorized users and sends pairing codes.
- Weixin group allowlists are not the same as personal DM pairing. Keep groups disabled unless the user gives exact group IDs and accepts the risk.
- The channel directory for Weixin is built from session history, not full contact enumeration.
- `context_token` is peer-specific and cached under `~/.hermes/weixin/accounts/<account_id>.context-tokens.json`.
- QR login and gateway startup use network access to Tencent endpoints; sandboxed/network-restricted shells may require escalation.
