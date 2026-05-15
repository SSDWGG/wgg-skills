#!/usr/bin/env python3
import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from net_fetch import fetch_url as resilient_fetch_url


HOME = Path.home()
TZ = ZoneInfo(os.environ.get("NEWS_DIGEST_TIMEZONE", "Asia/Shanghai"))
BASE_DIR = Path(os.environ.get("NEWS_DIGEST_DIR", str(HOME / ".codex" / "monitoring" / "daily-news"))).expanduser()
REPORT_DIR = BASE_DIR / "reports"
RUN_LOG = BASE_DIR / "runs.jsonl"
TEXT_LOG = HOME / ".codex" / "log" / "daily-news-digest.log"
NODE_BIN = os.environ.get("NEWS_DIGEST_NODE_BIN") or shutil.which("node") or "/usr/local/bin/node"
SEND_EMAIL_SCRIPT = Path(
    os.environ.get(
        "NEWS_DIGEST_SEND_EMAIL_SCRIPT",
        str(Path(__file__).resolve().with_name("send_email_with_attachment_via_email_mcp.mjs")),
    )
).expanduser()
EMAIL_ACCOUNT = os.environ.get("NEWS_DIGEST_EMAIL_ACCOUNT", "1982549567@qq.com")
EMAIL_TO = os.environ.get("NEWS_DIGEST_EMAIL_TO", EMAIL_ACCOUNT)
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SOURCES = [
    {
        "name": "NPR News RSS",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "type": "rss",
    },
    {
        "name": "Xinhua English",
        "url": "https://english.news.cn/",
        "type": "html",
    },
    {
        "name": "Xinhua World",
        "url": "https://english.news.cn/world/",
        "type": "html",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description="Build and email a Chinese morning/evening news digest.")
    parser.add_argument("--dry-run", action="store_true", help="Generate a report without sending email.")
    parser.add_argument("--force-email", action="store_true", help="Send a test email even if this is a manual run.")
    parser.add_argument("--max-items", type=int, default=18, help="Maximum total items to include.")
    parser.add_argument("--lookback-hours", type=int, default=24, help="Window label and freshness hint.")
    parser.add_argument(
        "--digest-name",
        choices=["auto", "morning", "evening"],
        default="auto",
        help="Digest label. auto uses morning before noon and evening after noon.",
    )
    return parser.parse_args()


def append_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def key_for(source, title):
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def fetch_url(url, user_agent=CHROME_UA):
    return resilient_fetch_url(url, user_agent=user_agent)


def absolutize_url(base_url, href):
    href = clean_text(href)
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return ""
    return urllib.parse.urljoin(base_url, href)


def parse_rss(xml_bytes, source_name):
    root = ET.fromstring(xml_bytes)
    records = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", ""))
        description = clean_text(item.findtext("description", ""))
        link = clean_text(item.findtext("link", ""))
        pub_raw = clean_text(item.findtext("pubDate", ""))
        try:
            published = email.utils.parsedate_to_datetime(pub_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=ZoneInfo("UTC"))
        except (TypeError, ValueError):
            published = None
        if not title or not link:
            continue
        records.append(make_record(source_name, title, description, link, published, "rss"))
    return records


def parse_html(html_bytes, source_name, base_url):
    text = html_bytes.decode("utf-8", errors="replace")
    records = []
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, flags=re.I | re.S):
        href, raw_title = match.groups()
        title = clean_text(raw_title)
        if not is_plausible_headline(title):
            continue
        link = absolutize_url(base_url, href)
        if not link or "english.news.cn" not in link:
            continue
        records.append(make_record(source_name, title, "", link, None, "html"))
    return records


def is_plausible_headline(title):
    if len(title) < 24 or len(title) > 180:
        return False
    lowered = title.lower()
    rejects = [
        "home",
        "more",
        "photos",
        "video",
        "services",
        "copyright",
        "about us",
        "editor's choice",
        "special reports",
    ]
    if lowered in rejects:
        return False
    if len(title.split()) < 4:
        return False
    return True


def classify(title, description):
    lowered = f"{title} {description}".lower()
    if any(term in lowered for term in ["gaza", "israel", "iran", "ukraine", "missile", "ceasefire", "nuclear", "yemen", "lebanon", "haiti"]) or re.search(r"\bwar\b|\bwars\b", lowered):
        return "国际冲突 / 安全"
    if any(term in lowered for term in ["china", "u.s.", "us-", "trump", "xi", "tariff", "trade", "diplomacy"]):
        return "大国关系 / 外交"
    if any(term in lowered for term in ["market", "stocks", "economy", "inflation", "rate", "oil", "prices", "debt"]):
        return "经济 / 市场"
    if any(term in lowered for term in ["artificial intelligence", "technology", "science", "space", "cyber"]) or re.search(r"\bai\b", lowered):
        return "科技 / AI"
    if any(term in lowered for term in ["court", "law", "judge", "police", "crime", "investigation", "cia"]):
        return "法律 / 安全"
    if any(term in lowered for term in ["health", "disease", "hospital", "therapy", "virus"]):
        return "公共卫生"
    if any(term in lowered for term in ["election", "president", "prime minister", "government", "congress", "minister"]):
        return "政治 / 治理"
    return "综合新闻"


def impact_level(topic):
    if topic in {"国际冲突 / 安全", "大国关系 / 外交"}:
        return "高"
    if topic in {"经济 / 市场", "法律 / 安全", "政治 / 治理"}:
        return "中"
    return "低"


def chinese_description(record):
    topic = record["topic_label"]
    source = record["source"]
    title = record["summary"]
    desc = record.get("description") or ""
    if desc:
        base = f"{source} 报道：{title}。报道要点是：{desc}"
    else:
        base = f"{source} 报道：{title}。"

    impact_map = {
        "国际冲突 / 安全": "可能影响地区安全局势、能源价格、外交斡旋和国际组织议程。",
        "大国关系 / 外交": "可能影响中美关系、贸易政策、供应链预期和外交沟通节奏。",
        "经济 / 市场": "可能影响投资者情绪、商品价格、企业成本或宏观政策预期。",
        "科技 / AI": "可能影响技术监管、产业竞争、科研投入或公众对新技术风险的认知。",
        "法律 / 安全": "可能影响执法、司法程序、国家安全叙事或公众信任。",
        "公共卫生": "可能影响医疗资源、公共卫生提醒、科研方向和社会风险感知。",
        "政治 / 治理": "可能影响政策执行、政府稳定性、选举叙事和公众议题优先级。",
        "综合新闻": "当前直接影响不明确，建议结合后续报道判断是否会升级为政策、市场或安全事件。",
    }
    return base, impact_map.get(topic, impact_map["综合新闻"])


def make_record(source, title, description, link, published, method):
    topic = classify(title, description)
    record = {
        "source": source,
        "summary": title,
        "description": description,
        "content_url": link,
        "published_at": published.isoformat() if published else "",
        "published_display": published.astimezone(TZ).strftime("%Y-%m-%d %H:%M") if published else "",
        "observed_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "topic_label": topic,
        "impact_level": impact_level(topic),
        "retrieval_method": method,
        "dedupe_key": key_for(source, title),
    }
    record["chinese_description"], record["impact"] = chinese_description(record)
    return record


def balanced_selection(records, max_items):
    grouped = {}
    source_order = []
    for record in records:
        source = record["source"]
        if source not in grouped:
            grouped[source] = []
            source_order.append(source)
        grouped[source].append(record)

    selected = []
    seen = set()
    while len(selected) < max_items:
        added = False
        for source in source_order:
            bucket = grouped[source]
            while bucket and bucket[0]["dedupe_key"] in seen:
                bucket.pop(0)
            if not bucket:
                continue
            record = bucket.pop(0)
            selected.append(record)
            seen.add(record["dedupe_key"])
            added = True
            if len(selected) >= max_items:
                break
        if not added:
            break
    return selected


def collect_records():
    records = []
    errors = []
    for source in SOURCES:
        try:
            payload = fetch_url(source["url"])
            if source["type"] == "rss":
                records.extend(parse_rss(payload, source["name"]))
            else:
                records.extend(parse_html(payload, source["name"], source["url"]))
        except Exception as exc:
            errors.append(f"{source['name']}: {exc}")

    deduped = {}
    for record in records:
        key = record["dedupe_key"]
        current = deduped.get(key)
        if current is None:
            deduped[key] = record
            continue
        if record.get("published_at", "") > current.get("published_at", ""):
            deduped[key] = record
    return sorted(deduped.values(), key=lambda item: item.get("published_at", "") or item["observed_at"], reverse=True), errors


def digest_label(now, requested):
    if requested == "morning":
        return "晨间新闻"
    if requested == "evening":
        return "晚间新闻"
    return "晨间新闻" if now.hour < 12 else "晚间新闻"


def build_markdown(now, label, records, errors, report_path, lookback_hours):
    start = now - timedelta(hours=lookback_hours)
    lines = [
        f"**Window:** {start.strftime('%Y-%m-%d %H:%M')}-{now.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai",
        f"**Digest:** {label}",
        f"**Sources:** NPR News RSS; Xinhua English homepage; Xinhua English /world/",
        f"**Report file:** `{report_path}`",
        "",
        "**重点摘要**",
    ]
    for item in records[:6]:
        lines.append(f"- [{item['topic_label']} / 影响：{item['impact_level']}] {item['chinese_description']} 可能影响：{item['impact']}")
    if not records:
        lines.append("- 本轮没有抓取到可用新闻。")

    lines.extend(["", "**新闻列表**"])
    for index, item in enumerate(records, start=1):
        lines.extend(
            [
                "",
                f"### {index}. {item['topic_label']}（影响：{item['impact_level']}）",
                f"- **时间/来源：** {item['published_display'] or item['observed_at']} · {item['source']}",
                f"- **中文说明：** {item['chinese_description']}",
                f"- **可能影响：** {item['impact']}",
                f"- **原始标题：** {item['summary']}",
                f"- **链接：** {item['content_url']}",
            ]
        )

    lines.extend(
        [
            "",
            "**来源说明**",
            "- NPR 使用官方 RSS 源。",
            "- 新华网英文首页和 /world/ 页面使用 Chrome User-Agent 获取公开页面。",
            "- 本脚本只读取公开网页和 RSS，不绕过登录、付费墙、反爬或隐私限制。",
        ]
    )
    if errors:
        lines.append("- 来源错误：" + "; ".join(errors))
    return "\n".join(lines) + "\n"


def build_html_body(now, label, records, errors, report_path):
    cards = []
    for item in records[:10]:
        level_color = "#dc2626" if item["impact_level"] == "高" else "#b45309" if item["impact_level"] == "中" else "#4b5563"
        cards.append(
            "<div style='border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:12px 0;background:#ffffff;'>"
            f"<div style='font-size:13px;line-height:20px;color:#6b7280;'>{html.escape(item['published_display'] or item['observed_at'])} · {html.escape(item['source'])}</div>"
            "<div style='margin-top:8px;'>"
            f"<span style='display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:700;'>{html.escape(item['topic_label'])}</span>"
            f"<span style='display:inline-block;margin-left:6px;color:{level_color};font-size:12px;font-weight:700;'>影响：{html.escape(item['impact_level'])}</span>"
            "</div>"
            f"<p style='font-size:15px;line-height:24px;color:#111827;margin:10px 0 0 0;'><strong>中文说明：</strong>{html.escape(item['chinese_description'])}</p>"
            f"<p style='font-size:15px;line-height:24px;color:#374151;margin:8px 0 0 0;'><strong>可能影响：</strong>{html.escape(item['impact'])}</p>"
            f"<div style='margin-top:10px;font-size:13px;line-height:20px;color:#6b7280;'>原始标题：{html.escape(item['summary'])}</div>"
            f"<div style='margin-top:8px;font-size:13px;line-height:20px;'><a href='{html.escape(item['content_url'])}' style='color:#2563eb;'>查看来源</a></div>"
            "</div>"
        )
    if not cards:
        cards.append("<div style='padding:12px;color:#374151;'>本轮没有抓取到可用新闻。</div>")
    error_note = f"<p style='color:#b45309;'>来源错误：{html.escape('; '.join(errors))}</p>" if errors else ""
    return f"""<!doctype html>
<html>
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,'PingFang SC','Microsoft YaHei',sans-serif;color:#111827;background:#f3f4f6;margin:0;padding:24px;">
    <div style="max-width:820px;margin:0 auto;">
      <div style="background:#111827;border-radius:14px 14px 0 0;padding:22px 24px;">
        <div style="font-size:13px;color:#9ca3af;">NPR + Xinhua News Digest</div>
        <h1 style="font-size:25px;line-height:34px;margin:6px 0 8px 0;color:#ffffff;">{html.escape(label)}摘要</h1>
        <p style="color:#d1d5db;margin:0;">{now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai · 候选 {len(records)} 条</p>
      </div>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 14px 14px;padding:18px 20px;">
        <p style="font-size:14px;line-height:22px;color:#374151;margin:0 0 12px 0;">每条新闻包含中文说明、可能影响、来源链接。Markdown 完整报告已作为附件发送：<code>{html.escape(str(report_path))}</code></p>
        {''.join(cards)}
        <div style="border-top:1px solid #e5e7eb;margin-top:16px;padding-top:12px;color:#6b7280;font-size:13px;line-height:20px;">
          来源：NPR RSS、新华网英文首页、新华网英文 /world/。新华网页面使用 Chrome User-Agent；不绕过登录、付费墙或反爬限制。
        </div>
        {error_note}
      </div>
    </div>
  </body>
</html>"""


def send_email(subject, html_body, report_path):
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
            str(report_path),
        ],
        input=html_body,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "email send failed")
    return result.stdout.strip()


def main():
    args = parse_args()
    now = datetime.now(TZ)
    label = digest_label(now, args.digest_name)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_LOG.parent.mkdir(parents=True, exist_ok=True)

    records, errors = collect_records()
    records = balanced_selection(records, max(args.max_items, 1))
    report_path = REPORT_DIR / f"daily-news-{label}-{now.strftime('%Y%m%d-%H%M%S')}.md"
    markdown = build_markdown(now, label, records, errors, report_path, args.lookback_hours)
    report_path.write_text(markdown, encoding="utf-8")

    email_sent = False
    email_result = ""
    if not args.dry_run:
        subject = f"{label}摘要 · NPR+新华社 · {now.strftime('%Y-%m-%d %H:%M')}"
        email_result = send_email(subject, build_html_body(now, label, records, errors, report_path), report_path)
        email_sent = True

    run_record = {
        "timestamp": now.isoformat(timespec="seconds"),
        "digest": label,
        "records": len(records),
        "emailSent": email_sent,
        "emailResult": email_result,
        "reportPath": str(report_path),
        "errors": errors,
        "dryRun": args.dry_run,
    }
    append_text(RUN_LOG, json.dumps(run_record, ensure_ascii=False, separators=(",", ":")))
    append_text(TEXT_LOG, f"[{run_record['timestamp']}] digest={label} records={len(records)} emailSent={email_sent} report={report_path}")
    print(json.dumps(run_record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
