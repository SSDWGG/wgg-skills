#!/usr/bin/env python3
import argparse
import http.client
import json
import os
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "https://codexzh.com"
DEFAULT_KEY_FILE = Path.home() / ".codex" / "codexzh-api-key"
RETRYABLE_ERRORS = (
    http.client.IncompleteRead,
    json.JSONDecodeError,
    ssl.SSLError,
    TimeoutError,
    UnicodeDecodeError,
    urllib.error.URLError,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Query CodexZH API usage and remaining quota."
    )
    parser.add_argument("--key", help="Use this API key for the query.")
    parser.add_argument(
        "--key-file",
        default=str(DEFAULT_KEY_FILE),
        help=f"Read the API key from this file. Default: {DEFAULT_KEY_FILE}",
    )
    parser.add_argument(
        "--save-key",
        help="Persist this API key to the key file with 0600 permissions, then query it.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL for CodexZH. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw API response JSON.",
    )
    return parser.parse_args()


def save_key(key: str, key_file: Path):
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key.strip() + "\n", encoding="utf-8")
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)


def load_key(args) -> str:
    if args.save_key:
        save_key(args.save_key, Path(args.key_file).expanduser())
        return args.save_key.strip()
    if args.key:
        return args.key.strip()

    env_key = os.environ.get("CODEXZH_API_KEY", "").strip()
    if env_key:
        return env_key

    key_path = Path(args.key_file).expanduser()
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()

    raise SystemExit(
        "No CodexZH API key found. Set CODEXZH_API_KEY, use --key, or run --save-key."
    )


def describe_network_error(error: Exception) -> str:
    if isinstance(error, urllib.error.URLError):
        return str(error.reason)
    if isinstance(error, http.client.IncompleteRead):
        return "incomplete response body"
    return str(error)


def fetch_usage(base_url: str, api_key: str):
    url = f"{base_url.rstrip('/')}/api/v1/usage/stats?{urllib.parse.urlencode({'key': api_key})}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "User-Agent": "codexzh-api-usage-skill/1.0",
        },
    )
    last_error = None

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return response.getcode(), payload
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {"success": False, "error": str(exc)}
            return exc.code, payload
        except RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(attempt)

    raise SystemExit(
        f"Network error while querying CodexZH: {describe_network_error(last_error)}"
    )


def quota_to_usd(raw_quota):
    return float(raw_quota or 0) / 500000.0


def format_money(value):
    return f"${value:.2f}"


def format_summary(data):
    today_used = float(data.get("todayUsed", 0) or 0)
    week_used = float(data.get("weekUsed", 0) or 0)
    total_used = float(data.get("totalUsed", 0) or 0)
    daily_quota = quota_to_usd(data.get("dailyQuota", 0))
    weekly_quota = quota_to_usd(data.get("weeklyQuota", 0))
    daily_remaining = max(daily_quota - today_used, 0.0)
    weekly_remaining = max(weekly_quota - week_used, 0.0)

    lines = [
        "CodexZH API 用量",
        f"今日剩余额度: {format_money(daily_remaining)} / 日度总额 {format_money(daily_quota)}",
        f"本周剩余额度: {format_money(weekly_remaining)} / 周度总额 {format_money(weekly_quota)}",
        f"今日消费: {data.get('todayUsedFormatted', format_money(today_used))}",
        f"本周消费: {data.get('weekUsedFormatted', format_money(week_used))}",
        f"累计消费: {data.get('totalUsedFormatted', format_money(total_used))}",
        f"今日调用: {data.get('todayCalls', 0)} 次",
        f"本周调用: {data.get('totalCalls', 0)} 次",
        f"RPM: {data.get('rpm', 0)}",
        f"TPM: {data.get('tpm', 0)}",
        f"订阅开始: {data.get('subscriptionStart') or '—'}",
        f"订阅到期: {data.get('subscriptionEnd') or '—'}",
    ]
    return "\n".join(lines)


def main():
    args = parse_args()
    api_key = load_key(args)
    status, payload = fetch_usage(args.base_url, api_key)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if status == 401:
        print("CodexZH API key 无效，请检查后重试。", file=sys.stderr)
        return 1

    if not payload.get("success"):
        error_code = payload.get("error")
        if error_code == "TOKEN_EXPIRED":
            print("CodexZH 套餐已到期，请续费后再使用。", file=sys.stderr)
            return 1
        print(f"查询失败: {error_code or 'unknown error'}", file=sys.stderr)
        return 1

    print(format_summary(payload.get("data", {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
