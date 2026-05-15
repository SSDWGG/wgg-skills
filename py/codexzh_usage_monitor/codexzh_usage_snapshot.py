#!/usr/bin/env python3
import argparse
import html as html_lib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


TOKEN_PER_USD = 500_000
HOME = Path.home()
SCRIPT_DIR = Path(__file__).resolve().parent
QUERY_SCRIPT = Path(
    os.environ.get(
        "CODEXZH_USAGE_QUERY_SCRIPT",
        str(SCRIPT_DIR / "query_codexzh_usage.py"),
    )
).expanduser()
NODE_BIN = Path(os.environ.get("CODEXZH_NODE_BIN", "/usr/local/bin/node")).expanduser()
SEND_EMAIL_SCRIPT = Path(
    os.environ.get("CODEXZH_SEND_EMAIL_SCRIPT", str(SCRIPT_DIR / "send_email_via_email_mcp.mjs"))
).expanduser()
EMAIL_ACCOUNT = os.environ.get("CODEXZH_EMAIL_ACCOUNT", "1982549567@qq.com")
EMAIL_TO = os.environ.get("CODEXZH_EMAIL_TO", EMAIL_ACCOUNT)
LOG_DIR = Path(os.environ.get("CODEXZH_USAGE_LOG_DIR", str(HOME / ".codex" / "log"))).expanduser()
JSONL_LOG = LOG_DIR / "codexzh-usage-snapshots.jsonl"
TEXT_LOG = LOG_DIR / "codexzh-usage-snapshots.log"
EMAIL_LOG = LOG_DIR / "codexzh-usage-email.log"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Query CodexZH usage, log a snapshot, and optionally send an email."
    )
    parser.add_argument(
        "--force-email",
        action="store_true",
        help="Send a manual test email even if total usage is unchanged.",
    )
    return parser.parse_args()


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def whole(value):
    return int(round(number(value)))


def append_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def load_previous_notified_snapshot(path: Path):
    if not path.exists():
        return None

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for raw_line in reversed(lines):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            snapshot = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if "totalUsedUsd" not in snapshot:
            continue
        if snapshot.get("emailSent", True) is False:
            continue
        return snapshot

    return None


def load_usage():
    result = subprocess.run(
        [str(QUERY_SCRIPT), "--json"],
        check=False,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "usage query failed")

    payload = json.loads(result.stdout)
    if not payload.get("success"):
        raise RuntimeError(f"usage query failed: {payload.get('error') or 'unknown error'}")
    return payload.get("data", {})


def format_int(value):
    return f"{whole(value):,}"


def format_usd(value):
    return f"${number(value):,.2f}"


def usage_percent(snapshot):
    quota = max(whole(snapshot.get("dailyQuotaTokens")), 1)
    used = whole(snapshot.get("todayTokensUsedEstimate"))
    return min(max(used / quota * 100, 0), 100)


def tokens_to_usd(tokens):
    return number(tokens) / TOKEN_PER_USD


def metric_card(label, value, note, accent):
    return f"""
      <td style="width:50%;padding:8px;">
        <div style="border:1px solid #e5e7eb;border-radius:12px;background:#ffffff;padding:16px 16px 14px 16px;">
          <div style="font-size:12px;line-height:18px;color:#6b7280;">{html_lib.escape(label)}</div>
          <div style="margin-top:6px;font-size:24px;line-height:30px;font-weight:700;color:#111827;letter-spacing:0;">{html_lib.escape(value)}</div>
          <div style="margin-top:7px;font-size:12px;line-height:18px;color:{accent};">{html_lib.escape(note)}</div>
        </div>
      </td>
    """


def spend_card(label, value, note, background, note_color):
    return f"""
      <td style="width:50%;padding:8px;">
        <div style="border-radius:14px;background:{background};padding:18px 18px 16px 18px;">
          <div style="font-size:13px;line-height:18px;color:#d1d5db;">{html_lib.escape(label)}</div>
          <div style="margin-top:8px;font-size:34px;line-height:40px;font-weight:800;color:#ffffff;letter-spacing:0;">{html_lib.escape(value)}</div>
          <div style="margin-top:8px;font-size:13px;line-height:18px;color:{note_color};">{html_lib.escape(note)}</div>
        </div>
      </td>
    """


def build_html_body(snapshot, body_line):
    percent = usage_percent(snapshot)
    status_color = "#059669"
    status_bg = "#d1fae5"
    if percent >= 85:
        status_color = "#dc2626"
        status_bg = "#fee2e2"
    elif percent >= 65:
        status_color = "#d97706"
        status_bg = "#fef3c7"

    timestamp = html_lib.escape(snapshot["timestampDisplay"])
    subscription_start = html_lib.escape(snapshot["subscriptionStart"] or "—")
    subscription_end = html_lib.escape(snapshot["subscriptionEnd"] or "—")
    progress_width = f"{percent:.1f}%"
    safe_line = html_lib.escape(body_line)

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f6fb;color:#111827;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;color:#f3f6fb;">
      今日消费 {format_usd(snapshot['todayUsedUsd'])}，本周消费 {format_usd(snapshot['weekUsedUsd'])}，今日已用 {progress_width}
    </div>
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f3f6fb;margin:0;padding:24px 0;">
      <tr>
        <td align="center" style="padding:0 14px;">
          <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:640px;border-collapse:collapse;">
            <tr>
              <td style="background:#111827;border-radius:18px 18px 0 0;padding:24px 24px 22px 24px;">
                <div style="font-size:13px;line-height:18px;color:#9ca3af;">CodexZH API</div>
                <div style="margin-top:6px;font-size:26px;line-height:34px;font-weight:800;color:#ffffff;letter-spacing:0;">今日 token 用量更新</div>
                <div style="margin-top:12px;">
                  <span style="display:inline-block;background:{status_bg};color:{status_color};font-size:13px;line-height:20px;font-weight:700;border-radius:999px;padding:5px 10px;">已用 {progress_width}</span>
                  <span style="display:inline-block;margin-left:8px;color:#d1d5db;font-size:13px;line-height:20px;">{timestamp}</span>
                </div>
              </td>
            </tr>
            <tr>
              <td style="background:#ffffff;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 18px 18px;padding:18px 16px 20px 16px;">
                <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;margin-bottom:2px;">
                  <tr>
                    {spend_card("今日消费", format_usd(snapshot['todayUsedUsd']), f"约 {format_int(snapshot['todayTokensUsedEstimate'])} tokens", "#111827", "#bfdbfe")}
                    {spend_card("本周消费", format_usd(snapshot['weekUsedUsd']), f"约 {format_int(snapshot['weekTokensUsedEstimate'])} tokens", "#0f766e", "#ccfbf1")}
                  </tr>
                </table>

                <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">
                  <tr>
                    {metric_card("今日调用", f"{format_int(snapshot['todayCalls'])} 次", f"RPM {snapshot['rpm']}", "#7c3aed")}
                    {metric_card("周额度", f"{format_usd(snapshot['weeklyRemainingUsd'])} 剩余", f"总额 {format_usd(snapshot['weeklyQuotaUsd'])}", "#0f766e")}
                  </tr>
                </table>

                <div style="padding:8px 8px 0 8px;">
                  <div style="margin-top:8px;margin-bottom:8px;font-size:13px;line-height:20px;color:#4b5563;">日额度进度</div>
                  <div style="height:12px;background:#eef2f7;border-radius:999px;overflow:hidden;">
                    <div style="height:12px;width:{progress_width};background:{status_color};border-radius:999px;"></div>
                  </div>
                  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:10px;border-collapse:collapse;">
                    <tr>
                      <td style="font-size:12px;line-height:18px;color:#6b7280;">0</td>
                      <td align="right" style="font-size:12px;line-height:18px;color:#6b7280;">{format_int(snapshot['dailyQuotaTokens'])} tokens</td>
                    </tr>
                  </table>
                </div>

                <div style="margin:18px 8px 0 8px;border:1px solid #e5e7eb;border-radius:12px;background:#f9fafb;padding:14px 16px;">
                  <div style="font-size:13px;line-height:20px;color:#374151;">{safe_line}</div>
                </div>

                <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:18px;border-collapse:collapse;">
                  <tr>
                    <td style="padding:0 8px;font-size:12px;line-height:19px;color:#6b7280;">
                      累计消费 <span style="color:#111827;font-weight:700;">${snapshot['totalUsedUsd']:.2f}</span>
                      <span style="color:#d1d5db;"> | </span>
                      订阅 {subscription_start} 至 {subscription_end}
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def send_email(snapshot, body_line):
    percent = usage_percent(snapshot)
    subject = f"CodexZH 用量更新 · 已用 {percent:.1f}% · {snapshot['timestampDisplay']}"
    body = build_html_body(snapshot, body_line)
    result = subprocess.run(
        [
            str(NODE_BIN),
            str(SEND_EMAIL_SCRIPT),
            "--account",
            EMAIL_ACCOUNT,
            "--to",
            EMAIL_TO,
            "--subject",
            subject,
            "--html",
        ],
        check=False,
        input=body,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "email send failed")
    append_text(EMAIL_LOG, f"[{snapshot['timestamp']}] sent to {EMAIL_TO}: {result.stdout.strip()}")


def main():
    args = parse_args()
    now = datetime.now().astimezone()
    try:
        data = load_usage()
        today_used_usd = number(data.get("todayUsed"))
        week_used_usd = number(data.get("weekUsed"))
        total_used_usd = number(data.get("totalUsed"))
        daily_quota_tokens = whole(data.get("dailyQuota"))
        weekly_quota_tokens = whole(data.get("weeklyQuota"))
        today_tokens_used = whole(today_used_usd * TOKEN_PER_USD)
        week_tokens_used = whole(week_used_usd * TOKEN_PER_USD)
        daily_tokens_remaining = max(daily_quota_tokens - today_tokens_used, 0)
        weekly_tokens_remaining = max(weekly_quota_tokens - week_tokens_used, 0)
        weekly_quota_usd = tokens_to_usd(weekly_quota_tokens)
        weekly_remaining_usd = max(weekly_quota_usd - week_used_usd, 0.0)

        snapshot = {
            "timestamp": now.isoformat(timespec="seconds"),
            "timestampDisplay": now.strftime("%Y年%m月%d日 %H时%M分%S秒"),
            "date": now.strftime("%Y-%m-%d"),
            "todayCalls": whole(data.get("todayCalls")),
            "todayUsedUsd": round(today_used_usd, 5),
            "weekUsedUsd": round(week_used_usd, 5),
            "totalUsedUsd": round(total_used_usd, 5),
            "todayTokensUsedEstimate": today_tokens_used,
            "weekTokensUsedEstimate": week_tokens_used,
            "dailyQuotaTokens": daily_quota_tokens,
            "dailyTokensRemainingEstimate": daily_tokens_remaining,
            "weeklyQuotaTokens": weekly_quota_tokens,
            "weeklyTokensRemainingEstimate": weekly_tokens_remaining,
            "weeklyQuotaUsd": round(weekly_quota_usd, 5),
            "weeklyRemainingUsd": round(weekly_remaining_usd, 5),
            "rpm": whole(data.get("rpm")),
            "tpm": whole(data.get("tpm")),
            "subscriptionStart": data.get("subscriptionStart"),
            "subscriptionEnd": data.get("subscriptionEnd"),
        }

        previous_snapshot = load_previous_notified_snapshot(JSONL_LOG)
        previous_total_used_usd = None
        total_used_usd_delta = None
        usage_changed = True
        if previous_snapshot:
            previous_total_used_usd = round(number(previous_snapshot.get("totalUsedUsd")), 5)
            total_used_usd_delta = round(snapshot["totalUsedUsd"] - previous_total_used_usd, 5)
            usage_changed = total_used_usd_delta != 0

        snapshot.update(
            {
                "previousNotifiedTotalUsedUsd": previous_total_used_usd,
                "totalUsedUsdDelta": total_used_usd_delta,
                "usageChanged": usage_changed,
                "forceEmail": args.force_email,
                "emailSent": False,
            }
        )

        LOG_DIR.mkdir(parents=True, exist_ok=True)

        if total_used_usd_delta is None:
            delta_text = "首次提醒"
        else:
            sign = "+" if total_used_usd_delta > 0 else ""
            delta_text = f"较上次提醒累计 {sign}${total_used_usd_delta:.5f}"

        line = (
            f"[{snapshot['timestamp']}] "
            f"今日调用 {snapshot['todayCalls']} 次 | "
            f"今日消费 ${today_used_usd:.2f} | "
            f"本周消费 ${week_used_usd:.2f} | "
            f"累计消费 ${snapshot['totalUsedUsd']:.5f} | "
            f"{delta_text} | "
            f"今日已用约 {today_tokens_used:,} tokens | "
            f"今日剩余约 {daily_tokens_remaining:,}/{daily_quota_tokens:,} tokens | "
            f"RPM {snapshot['rpm']} | TPM {snapshot['tpm']:,}"
        )

        if args.force_email:
            line = f"{line} | 手动测试强制发送"
        elif not usage_changed:
            snapshot["emailSkippedReason"] = "total usage unchanged"
            append_text(JSONL_LOG, json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
            line = f"{line} | 总用量未变，跳过邮件"
            append_text(TEXT_LOG, line)
            print(line)
            return 0

        send_email(snapshot, line)
        snapshot["emailSent"] = True
        append_text(JSONL_LOG, json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
        append_text(TEXT_LOG, line)
        print(line)
        return 0
    except Exception as exc:
        line = f"[{now.isoformat(timespec='seconds')}] ERROR {exc}"
        append_text(TEXT_LOG, line)
        print(line, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
