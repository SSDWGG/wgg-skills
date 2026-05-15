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
TZ = ZoneInfo(os.environ.get("WEATHER_MONITOR_TIMEZONE", "Asia/Shanghai"))
BASE_DIR = Path(os.environ.get("WEATHER_MONITOR_DIR", str(HOME / ".codex" / "monitoring" / "hangzhou-weather"))).expanduser()
REPORT_DIR = BASE_DIR / "reports"
RUN_LOG = BASE_DIR / "runs.jsonl"
TEXT_LOG = HOME / ".codex" / "log" / "hangzhou-weather-monitor.log"
NODE_BIN = os.environ.get("WEATHER_MONITOR_NODE_BIN") or "/usr/local/bin/node"
SEND_EMAIL_SCRIPT = Path(
    os.environ.get(
        "WEATHER_MONITOR_SEND_EMAIL_SCRIPT",
        str(Path(__file__).resolve().with_name("send_email_with_attachment_via_email_mcp.mjs")),
    )
).expanduser()
EMAIL_ACCOUNT = os.environ.get("WEATHER_MONITOR_EMAIL_ACCOUNT", "1982549567@qq.com")
EMAIL_TO = os.environ.get("WEATHER_MONITOR_EMAIL_TO", EMAIL_ACCOUNT)
LATITUDE = 30.25
LONGITUDE = 120.17


WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷雨",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Email tomorrow weather for Hangzhou Shangcheng.")
    parser.add_argument("--dry-run", action="store_true", help="Generate a report without sending email.")
    return parser.parse_args()


def append_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def load_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={LATITUDE}&longitude={LONGITUDE}"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max"
        "&timezone=Asia%2FShanghai&forecast_days=3"
    )
    payload = json.loads(fetch_url(url, user_agent="Codex Hangzhou weather monitor/1.0").decode("utf-8"))
    daily = payload["daily"]
    tomorrow = (datetime.now(TZ).date() + timedelta(days=1)).isoformat()
    index = daily["time"].index(tomorrow) if tomorrow in daily["time"] else min(1, len(daily["time"]) - 1)
    return {
        "date": daily["time"][index],
        "weather_code": daily["weather_code"][index],
        "weather": WEATHER_CODES.get(daily["weather_code"][index], f"WMO {daily['weather_code'][index]}"),
        "temp_max": daily["temperature_2m_max"][index],
        "temp_min": daily["temperature_2m_min"][index],
        "rain_probability": daily["precipitation_probability_max"][index],
        "rain_sum": daily["precipitation_sum"][index],
        "wind_max": daily["wind_speed_10m_max"][index],
    }


def commute_advice(weather):
    tips = []
    if weather["rain_probability"] >= 50 or weather["rain_sum"] >= 1:
        tips.append("带伞，尽量预留通勤缓冲时间。")
    elif weather["rain_probability"] >= 20:
        tips.append("有降水可能，包里放一把轻便伞更稳。")
    else:
        tips.append("降水概率低，正常通勤即可。")
    if weather["temp_max"] >= 30:
        tips.append("白天偏热，建议穿透气衣物并注意补水。")
    elif weather["temp_min"] <= 10:
        tips.append("早晚偏冷，建议加外套。")
    else:
        tips.append("气温相对舒适，按日常上班穿着即可。")
    if weather["wind_max"] >= 28:
        tips.append("风力偏大，骑车或撑伞注意安全。")
    return " ".join(tips)


def build_markdown(now, weather, report_path):
    advice = commute_advice(weather)
    return f"""**时间:** {now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai
**地点:** 杭州市上城区
**日期:** {weather['date']}（明日）
**数据源:** Open-Meteo public forecast API
**报告文件:** `{report_path}`

**明日天气**
- 天气：{weather['weather']}
- 气温：{weather['temp_min']:.1f}°C - {weather['temp_max']:.1f}°C
- 降水概率：{weather['rain_probability']}%
- 预计降水量：{weather['rain_sum']} mm
- 最大风速：{weather['wind_max']:.1f} km/h

**上班前建议**
{advice}
"""


def build_html_body(now, weather, report_path):
    advice = commute_advice(weather)
    rain_color = "#2563eb" if weather["rain_probability"] >= 30 else "#059669"
    return f"""<!doctype html>
<html>
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,'PingFang SC','Microsoft YaHei',sans-serif;background:#f3f4f6;color:#111827;margin:0;padding:24px;">
    <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
      <div style="background:#0f172a;color:#fff;padding:22px 24px;">
        <div style="font-size:13px;color:#cbd5e1;">Weather Monitor</div>
        <h1 style="margin:6px 0 8px 0;font-size:25px;line-height:34px;">杭州上城区明日天气</h1>
        <div style="color:#cbd5e1;">{now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai · 预报日期 {weather['date']}</div>
      </div>
      <div style="padding:20px 24px;">
        <div style="font-size:32px;line-height:40px;font-weight:800;">{weather['weather']} · {weather['temp_min']:.1f}°C - {weather['temp_max']:.1f}°C</div>
        <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
          <span style="display:inline-block;padding:8px 10px;border-radius:999px;background:#eff6ff;color:{rain_color};font-weight:700;">降水概率 {weather['rain_probability']}%</span>
          <span style="display:inline-block;padding:8px 10px;border-radius:999px;background:#f8fafc;color:#334155;font-weight:700;">降水 {weather['rain_sum']} mm</span>
          <span style="display:inline-block;padding:8px 10px;border-radius:999px;background:#f8fafc;color:#334155;font-weight:700;">最大风速 {weather['wind_max']:.1f} km/h</span>
        </div>
        <div style="margin-top:18px;padding:14px 16px;border:1px solid #e5e7eb;border-radius:10px;background:#f9fafb;line-height:24px;">
          <strong>上班前建议：</strong>{advice}
        </div>
        <p style="color:#6b7280;font-size:13px;line-height:20px;margin-top:16px;">完整 Markdown 报告已附上：<code>{report_path}</code></p>
      </div>
    </div>
  </body>
</html>"""


def send_email(subject, body, attachment):
    result = subprocess.run(
        [
            NODE_BIN,
            str(SEND_EMAIL_SCRIPT),
            "--account",
            EMAIL_ACCOUNT,
            "--to",
            EMAIL_TO,
            "--subject",
            subject,
            "--html",
            "--attachment",
            str(attachment),
        ],
        input=body,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "email send failed")
    return result.stdout.strip()


def main():
    args = parse_args()
    now = datetime.now(TZ)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_LOG.parent.mkdir(parents=True, exist_ok=True)
    weather = load_weather()
    report_path = REPORT_DIR / f"hangzhou-shangcheng-weather-{now.strftime('%Y%m%d-%H%M%S')}.md"
    report_path.write_text(build_markdown(now, weather, report_path), encoding="utf-8")
    email_sent = False
    email_result = ""
    if not args.dry_run:
        subject = f"杭州上城区明日天气 · {weather['weather']} · {weather['temp_min']:.0f}-{weather['temp_max']:.0f}°C"
        email_result = send_email(subject, build_html_body(now, weather, report_path), report_path)
        email_sent = True
    run = {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": weather["date"],
        "emailSent": email_sent,
        "emailResult": email_result,
        "reportPath": str(report_path),
        "dryRun": args.dry_run,
    }
    append_text(RUN_LOG, json.dumps(run, ensure_ascii=False, separators=(",", ":")))
    append_text(TEXT_LOG, f"[{run['timestamp']}] date={weather['date']} emailSent={email_sent} report={report_path}")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
