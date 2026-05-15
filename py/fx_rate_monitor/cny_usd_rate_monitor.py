#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from net_fetch import fetch_url


HOME = Path.home()
TZ = ZoneInfo(os.environ.get("FX_MONITOR_TIMEZONE", "Asia/Shanghai"))
BASE_DIR = Path(os.environ.get("FX_MONITOR_DIR", str(HOME / ".codex" / "monitoring" / "cny-usd-rate"))).expanduser()
REPORT_DIR = BASE_DIR / "reports"
RUN_LOG = BASE_DIR / "runs.jsonl"
TEXT_LOG = HOME / ".codex" / "log" / "cny-usd-rate-monitor.log"
NODE_BIN = os.environ.get("FX_MONITOR_NODE_BIN") or "/usr/local/bin/node"
SEND_EMAIL_SCRIPT = Path(
    os.environ.get(
        "FX_MONITOR_SEND_EMAIL_SCRIPT",
        str(Path(__file__).resolve().with_name("send_email_with_attachment_via_email_mcp.mjs")),
    )
).expanduser()
EMAIL_ACCOUNT = os.environ.get("FX_MONITOR_EMAIL_ACCOUNT", "1982549567@qq.com")
EMAIL_TO = os.environ.get("FX_MONITOR_EMAIL_TO", EMAIL_ACCOUNT)


def parse_args():
    parser = argparse.ArgumentParser(description="Email CNY/USD exchange-rate digest with recent trend.")
    parser.add_argument("--dry-run", action="store_true", help="Generate files without sending email.")
    parser.add_argument("--days", type=int, default=10, help="Calendar days to query for recent exchange-rate history.")
    return parser.parse_args()


def append_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def load_yahoo_rates(days):
    start = int((datetime.now(TZ) - timedelta(days=days)).timestamp())
    end = int((datetime.now(TZ) + timedelta(days=1)).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/CNY=X?period1={start}&period2={end}&interval=1d"
    payload = json.loads(fetch_url(url, user_agent="Mozilla/5.0 Codex FX monitor/1.0").decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [])[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []

    rates_by_date = {}
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(timestamp, TZ).date().isoformat()
        usd_to_cny = float(close)
        rates_by_date[day] = {
            "date": day,
            "cny_to_usd": 1 / usd_to_cny,
            "usd_to_cny": usd_to_cny,
            "source": "Yahoo Finance 日线",
            "data_time": day,
        }

    latest_price = meta.get("regularMarketPrice")
    latest_time = meta.get("regularMarketTime")
    if latest_price is not None:
        latest_dt = datetime.fromtimestamp(int(latest_time), TZ) if latest_time else datetime.now(TZ)
        day = latest_dt.date().isoformat()
        usd_to_cny = float(latest_price)
        rates_by_date[day] = {
            "date": day,
            "cny_to_usd": 1 / usd_to_cny,
            "usd_to_cny": usd_to_cny,
            "source": "Yahoo Finance 最新报价",
            "data_time": latest_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }

    rates = [rates_by_date[day] for day in sorted(rates_by_date)]
    if not rates:
        raise RuntimeError("Yahoo Finance returned no usable USD/CNY rates")
    return rates


def load_frankfurter_rates(days):
    end = datetime.now(TZ).date()
    start = end - timedelta(days=days)
    url = f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}?from=CNY&to=USD"
    payload = json.loads(fetch_url(url, user_agent="Codex FX monitor/1.0").decode("utf-8"))
    rates = []
    for day, item in sorted((payload.get("rates") or {}).items()):
        usd = item.get("USD")
        if usd is None:
            continue
        rates.append({
            "date": day,
            "cny_to_usd": float(usd),
            "usd_to_cny": 1 / float(usd),
            "source": "Frankfurter 日度汇率",
            "data_time": day,
        })
    if not rates:
        latest_url = "https://api.frankfurter.app/latest?from=CNY&to=USD"
        latest = json.loads(fetch_url(latest_url, user_agent="Codex FX monitor/1.0").decode("utf-8"))
        usd = float(latest["rates"]["USD"])
        rates.append({
            "date": latest["date"],
            "cny_to_usd": usd,
            "usd_to_cny": 1 / usd,
            "source": "Frankfurter 日度汇率",
            "data_time": latest["date"],
        })
    return rates


def load_rates(days):
    try:
        return load_yahoo_rates(days)
    except Exception as yahoo_error:
        rates = load_frankfurter_rates(days)
        for item in rates:
            item["source"] = f"{item['source']}（Yahoo Finance 获取失败后降级：{yahoo_error}）"
        return rates


def sparkline(values):
    ticks = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    low, high = min(values), max(values)
    if high == low:
        return ticks[0] * len(values)
    return "".join(ticks[round((value - low) / (high - low) * (len(ticks) - 1))] for value in values)


def build_svg(rates, path):
    width, height = 760, 260
    margin = 44
    values = [item["usd_to_cny"] for item in rates]
    low, high = min(values), max(values)
    pad = max((high - low) * 0.15, 0.01)
    low -= pad
    high += pad

    points = []
    for index, item in enumerate(rates):
        x = margin + index * ((width - 2 * margin) / max(len(rates) - 1, 1))
        y = height - margin - ((item["usd_to_cny"] - low) / (high - low)) * (height - 2 * margin)
        points.append((x, y))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    labels = "\n".join(
        f'<text x="{x:.1f}" y="{height - 16}" font-size="11" text-anchor="middle" fill="#6b7280">{item["date"][5:]}</text>'
        for (x, _), item in zip(points, rates)
    )
    circles = "\n".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2563eb" />' for x, y in points)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{margin}" y="26" font-size="18" font-family="Arial" fill="#111827">USD/CNY 近几日曲线</text>
  <text x="{width - margin}" y="26" font-size="12" font-family="Arial" text-anchor="end" fill="#6b7280">越高代表美元相对人民币更强</text>
  <line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#d1d5db"/>
  <line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#d1d5db"/>
  <polyline points="{polyline}" fill="none" stroke="#2563eb" stroke-width="3"/>
  {circles}
  {labels}
  <text x="{margin + 4}" y="{margin + 4}" font-size="11" fill="#6b7280">{high:.4f}</text>
  <text x="{margin + 4}" y="{height - margin - 6}" font-size="11" fill="#6b7280">{low:.4f}</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def build_markdown(now, rates, report_path, chart_path):
    latest = rates[-1]
    previous = rates[-2] if len(rates) >= 2 else latest
    delta = latest["usd_to_cny"] - previous["usd_to_cny"]
    pct = delta / previous["usd_to_cny"] * 100 if previous["usd_to_cny"] else 0
    line = sparkline([item["usd_to_cny"] for item in rates])
    rows = "\n".join(
        f"| {item['date']} | {item['cny_to_usd']:.6f} | {item['usd_to_cny']:.4f} |"
        for item in rates
    )
    return f"""**时间:** {now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai
**主题:** 人民币兑美元汇率
**数据源:** {latest.get('source', 'Yahoo Finance / Frankfurter')}
**数据时间:** {latest.get('data_time', latest['date'])}
**报告文件:** `{report_path}`
**曲线文件:** `{chart_path}`

**今日汇率**
- 1 人民币 ≈ {latest['cny_to_usd']:.6f} 美元
- 1 美元 ≈ {latest['usd_to_cny']:.4f} 人民币
- 较上一数据日变化：{delta:+.4f} CNY/USD（{pct:+.3f}%）

**近几日曲线（USD/CNY，越高代表美元相对人民币更强）**

`{line}`

| 日期 | CNY→USD | USD→CNY |
|---|---:|---:|
{rows}

**提示**
- 最新报价来自公开免费源，可能有延迟，不等同于银行实时成交价。
- 如果你要换汇或交易，请以银行/券商实际报价为准。
"""


def build_html_body(now, rates, report_path, chart_path):
    latest = rates[-1]
    previous = rates[-2] if len(rates) >= 2 else latest
    delta = latest["usd_to_cny"] - previous["usd_to_cny"]
    pct = delta / previous["usd_to_cny"] * 100 if previous["usd_to_cny"] else 0
    trend = sparkline([item["usd_to_cny"] for item in rates])
    table_rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #e5e7eb;'>{item['date']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{item['cny_to_usd']:.6f}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{item['usd_to_cny']:.4f}</td></tr>"
        for item in rates
    )
    return f"""<!doctype html>
<html>
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,'PingFang SC','Microsoft YaHei',sans-serif;background:#f3f4f6;color:#111827;margin:0;padding:24px;">
    <div style="max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
      <div style="background:#111827;color:#fff;padding:22px 24px;">
        <div style="font-size:13px;color:#9ca3af;">Exchange Rate Monitor</div>
        <h1 style="margin:6px 0 8px 0;font-size:25px;line-height:34px;">人民币兑美元汇率</h1>
        <div style="color:#d1d5db;">{now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai · 数据日期 {latest['date']}</div>
      </div>
      <div style="padding:20px 24px;">
        <div style="font-size:34px;line-height:42px;font-weight:800;">1 USD ≈ {latest['usd_to_cny']:.4f} CNY</div>
        <div style="margin-top:6px;color:#374151;">1 CNY ≈ {latest['cny_to_usd']:.6f} USD · 较上一数据日 {delta:+.4f} ({pct:+.3f}%)</div>
        <div style="margin-top:6px;color:#6b7280;font-size:13px;">数据源：{latest.get('source', 'Yahoo Finance / Frankfurter')} · 数据时间：{latest.get('data_time', latest['date'])}</div>
        <div style="margin-top:18px;padding:14px 16px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;">
          <div style="font-size:13px;color:#6b7280;">近几日曲线（USD/CNY）</div>
          <div style="font-size:28px;letter-spacing:2px;margin-top:8px;color:#2563eb;">{trend}</div>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:18px;font-size:14px;">
          <thead><tr><th align="left" style="padding:8px;border-bottom:1px solid #d1d5db;">日期</th><th align="right" style="padding:8px;border-bottom:1px solid #d1d5db;">CNY→USD</th><th align="right" style="padding:8px;border-bottom:1px solid #d1d5db;">USD→CNY</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
        <p style="color:#6b7280;font-size:13px;line-height:20px;margin-top:16px;">完整 Markdown 报告和 SVG 曲线已附上。公开免费报价可能有延迟，请以银行实际报价为准。</p>
      </div>
    </div>
  </body>
</html>"""


def send_email(subject, body, attachments):
    args = [
        NODE_BIN,
        str(SEND_EMAIL_SCRIPT),
        "--account",
        EMAIL_ACCOUNT,
        "--to",
        EMAIL_TO,
        "--subject",
        subject,
        "--html",
    ]
    for attachment in attachments:
        args.extend(["--attachment", str(attachment)])
    result = subprocess.run(args, input=body, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "email send failed")
    return result.stdout.strip()


def main():
    args = parse_args()
    now = datetime.now(TZ)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_LOG.parent.mkdir(parents=True, exist_ok=True)
    rates = load_rates(args.days)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    report_path = REPORT_DIR / f"cny-usd-rate-{stamp}.md"
    chart_path = REPORT_DIR / f"cny-usd-rate-{stamp}.svg"
    build_svg(rates, chart_path)
    report_path.write_text(build_markdown(now, rates, report_path, chart_path), encoding="utf-8")
    email_sent = False
    email_result = ""
    if not args.dry_run:
        latest = rates[-1]
        subject = f"人民币兑美元汇率 · 1 USD≈{latest['usd_to_cny']:.4f} CNY · {latest['date']}"
        email_result = send_email(subject, build_html_body(now, rates, report_path, chart_path), [report_path, chart_path])
        email_sent = True
    run = {
        "timestamp": now.isoformat(timespec="seconds"),
        "records": len(rates),
        "emailSent": email_sent,
        "emailResult": email_result,
        "reportPath": str(report_path),
        "chartPath": str(chart_path),
        "dryRun": args.dry_run,
    }
    append_text(RUN_LOG, json.dumps(run, ensure_ascii=False, separators=(",", ":")))
    append_text(TEXT_LOG, f"[{run['timestamp']}] records={len(rates)} emailSent={email_sent} report={report_path}")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
