#!/usr/bin/env python3
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
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
FETCH_PROXY = os.environ.get("NEWS_DIGEST_PROXY") or os.environ.get("MONITOR_PROXY") or ""
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Primary: CCTV News homepage; secondary: CGTN RSS (English)
SOURCES = [
    {
        "name": "央视新闻",
        "url": "https://news.cctv.com/",
        "type": "cctv_homepage",
    },
    {
        "name": "CGTN",
        "url": "https://www.cgtn.com/subscribe/rss/section/world.xml",
        "type": "rss",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description="Build and email a Chinese morning/evening news digest from CCTV News.")
    parser.add_argument("--dry-run", action="store_true", help="Generate a report without sending email.")
    parser.add_argument("--force-email", action="store_true", help="Send email even if manual run.")
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


def clean_html_entities(text):
    text = text.replace("&ldquo;", "“").replace("&rdquo;", "”")
    text = text.replace("&mdash;", "—").replace("&ndash;", "–")
    text = text.replace("&lsquo;", "‘").replace("&rsquo;", "’")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ")
    text = text.replace("&quot;", '"')
    return text


def key_for(source, title):
    normalized = re.sub(r"[^a-z0-9一-鿿]+", " ", title.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def fetch_url(url, user_agent=CHROME_UA):
    return resilient_fetch_url(url, user_agent=user_agent, proxy=FETCH_PROXY or None)


def absolutize_url(base_url, href):
    href = (href or "").strip()
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return ""
    return urllib.parse.urljoin(base_url, href)


# ---------------------------------------------------------------------------
# CCTV article extraction
# ---------------------------------------------------------------------------

def extract_cctv_article(article_url):
    """Fetch a CCTV news article page and extract title, description, and full body."""
    try:
        raw = fetch_url(article_url, user_agent=CHROME_UA).decode("utf-8", errors="replace")
    except Exception:
        return None

    # Title from <title>
    title_match = re.search(r"<title>(.*?)</title>", raw)
    title = ""
    if title_match:
        title = title_match.group(1)
        title = re.sub(r"[_|\-].*?(央视网|新闻频道|cctv\.com).*$", "", title, flags=re.I).strip()

    # Meta description
    desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', raw, re.I)
    description = clean_html_entities(desc_match.group(1)) if desc_match else ""

    # Meta source
    src_match = re.search(r'<meta\s+name=["\']source["\']\s+content=["\']([^"\']+)["\']', raw, re.I)
    source = src_match.group(1) if src_match else "央视新闻"

    # Meta keywords
    kw_match = re.search(r'<meta\s+name=["\']keywords["\']\s+content=["\']([^"\']+)["\']', raw, re.I)
    keywords = kw_match.group(1) if kw_match else ""

    # Article body from var contentdate — find closing quote before </script>
    body = ""
    start_marker = "var contentdate  = '"
    start_idx = raw.find(start_marker)
    if start_idx >= 0:
        value_start = start_idx + len(start_marker)
        # Find the closing single quote that is followed by optional whitespace + </script>
        end_match = re.search(r"'\s*</script>", raw[value_start:])
        if end_match:
            body = raw[value_start:value_start + end_match.start()]
            body = clean_html_entities(body)
            # Remove video/photo embed placeholders
            body = re.sub(r"\[!--begin:htmlVideoCode--\].*?\[!--end:htmlVideoCode--\]", "", body)
            body = re.sub(r"\[!--begin:htmlPhotoCode--\].*?\[!--end:htmlPhotoCode--\]", "", body)
            # Strip remaining HTML tags
            body = re.sub(r"<img[^>]*/?>", "[图]", body)
            body = re.sub(r"<br\s*/?>", "\n", body)
            body = re.sub(r"</?p[^>]*>", "\n", body)
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\n{3,}", "\n\n", body)
            body = re.sub(r" +", " ", body)
            body = re.sub(r"\n +", "\n", body)
            lines = [line.strip() for line in body.split("\n")]
            body = "\n".join(line for line in lines if line)
    if not body and description:
        body = description

    return {
        "title": title,
        "description": description,
        "body": body.strip(),
        "source": source,
        "keywords": keywords,
    }


def parse_cctv_homepage(html_bytes, source_name, base_url):
    """Parse CCTV News homepage, extract article links, then fetch full content."""
    text = html_bytes.decode("utf-8", errors="replace")
    records = []

    # Find article links: /2026/05/19/ARTIxxx.shtml
    seen_urls = set()
    for match in re.finditer(r'href="(https?://news\.cctv\.com/\d{4}/\d{2}/\d{2}/ARTI[a-zA-Z0-9]+\.shtml)"', text):
        url = match.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if len(seen_urls) > 30:
            break

    for article_url in seen_urls:
        article = extract_cctv_article(article_url)
        if not article or not article["title"] or len(article["title"]) < 10:
            continue
        record = make_cctv_record(source_name, article, article_url)
        if record:
            records.append(record)
        if len(records) >= 20:
            break
    return records


def make_cctv_record(source_name, article, url):
    title = article["title"]
    description = article["description"]
    body = article["body"]
    keywords = article["keywords"]

    topic = classify_cctv(title + " " + description + " " + keywords)
    record = {
        "source": f"{source_name} · {article['source']}",
        "summary": title,
        "description": description,
        "text_excerpt": body if body else description,
        "content_url": url,
        "published_at": "",
        "published_display": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "observed_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "topic_label": topic,
        "impact_level": impact_level(topic),
        "retrieval_method": "cctv-article",
        "dedupe_key": key_for(source_name, title),
    }
    record["chinese_description"], record["impact"] = cctv_chinese_description(record)
    return record


def classify_cctv(combined_text):
    lowered = combined_text.lower()
    if any(t in lowered for t in ["战争", "冲突", "导弹", "核武器", "军事", "军演", "袭击", "打击", "巴以", "俄乌", "坦克", "部队", "国防", "武器"]):
        return "国际安全 / 军事"
    if any(t in lowered for t in ["外交", "中美", "中俄", "中欧", "出访", "会谈", "关税", "贸易战", "制裁", "习近平", "主席", "国事", "元首", "联合国"]):
        return "大国外交 / 政治"
    if any(t in lowered for t in ["经济", "gdp", "金融", "股市", "通胀", "房地产", "就业", "消费", "产业", "制造", "贸易", "工程", "南水北调", "建设", "企业", "投资", "项目"]):
        return "经济 / 产业"
    if any(t in lowered for t in ["科技", "ai", "人工智能", "芯片", "航天", "卫星", "5g", "6g", "新能源", "电池", "互联网", "数据", "智能"]):
        return "科技 / 创新"
    if any(t in lowered for t in ["法院", "法律", "公安", "犯罪", "反腐", "调查", "司法", "检察", "违法", "扫黑"]):
        return "法治 / 社会"
    if any(t in lowered for t in ["医疗", "健康", "疫情", "疾病", "医保", "药品", "医生", "医院", "疫苗"]):
        return "医疗 / 健康"
    if any(t in lowered for t in ["教育", "高考", "大学", "学生", "学校", "教师", "课程"]):
        return "教育 / 人才"
    if any(t in lowered for t in ["气候", "环境", "生态", "灾害", "地震", "洪水", "台风", "污染", "减排", "碳"]):
        return "环境 / 气候"
    if any(t in lowered for t in ["文化", "体育", "奥运", "电影", "艺术", "旅游", "音乐", "文学", "非遗"]):
        return "文化 / 体育"
    if any(t in lowered for t in ["民生", "住房", "交通", "社保", "养老", "收入", "高铁", "公交", "巴士", "地铁", "补贴", "物价", "出行", "票价"]):
        return "民生 / 社会"
    return "综合要闻"


def impact_level(topic):
    high_topics = {"国际安全 / 军事", "大国外交 / 政治"}
    mid_topics = {"经济 / 产业", "法治 / 社会", "科技 / 创新", "民生 / 社会"}
    if topic in high_topics:
        return "高"
    if topic in mid_topics:
        return "中"
    return "低"


def cctv_chinese_description(record):
    topic = record["topic_label"]
    title = record["summary"]
    desc = record.get("description") or ""
    prefix = f"央视新闻：{title}"
    if desc:
        prefix += f"。摘要：{desc}"
    impact_map = {
        "国际安全 / 军事": "可能影响地区安全局势、国际关系格局及我国周边战略环境。",
        "大国外交 / 政治": "可能影响中美关系走向、全球治理格局及我国外交策略。",
        "经济 / 产业": "可能影响市场预期、产业政策走向及宏观经济运行。",
        "科技 / 创新": "可能影响技术竞争格局、科研投入方向及产业升级节奏。",
        "法治 / 社会": "可能影响司法公信力、社会秩序及政策执行力度。",
        "医疗 / 健康": "可能影响公共卫生政策、医疗资源配置及社会健康意识。",
        "教育 / 人才": "可能影响教育资源配置、人才培养方向及社会公平。",
        "环境 / 气候": "可能影响环保政策力度、能源转型及公众环保意识。",
        "文化 / 体育": "可能影响文化产业走向、民族凝聚力及国际文化交流。",
        "民生 / 社会": "可能影响居民生活质量、社会稳定性及政策满意度。",
        "综合要闻": "当前直接影响不明确，建议关注后续跟进报道判断实际影响。",
    }
    return prefix, impact_map.get(topic, impact_map["综合要闻"])


# ---------------------------------------------------------------------------
# RSS parsing (CGTN fallback)
# ---------------------------------------------------------------------------

def parse_rss(xml_bytes, source_name):
    root = ET.fromstring(xml_bytes)
    records = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", ""))
        description = clean_text(item.findtext("description", ""))
        link = clean_text(item.findtext("link", ""))
        if not title or not link or len(title) < 15:
            continue
        topic = classify_cctv(title + " " + description)
        records.append({
            "source": source_name,
            "summary": title,
            "description": description,
            "text_excerpt": description if description else title,
            "content_url": link,
            "published_at": "",
            "published_display": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
            "observed_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "topic_label": topic,
            "impact_level": impact_level(topic),
            "retrieval_method": "rss",
            "dedupe_key": key_for(source_name, title),
            "chinese_description": "",
            "impact": "",
        })
        records[-1]["chinese_description"], records[-1]["impact"] = cctv_chinese_description(records[-1])
    return records


# ---------------------------------------------------------------------------
# Collection & selection
# ---------------------------------------------------------------------------

def collect_records():
    records = []
    errors = []
    for src in SOURCES:
        try:
            payload = fetch_url(src["url"])
            if src["type"] == "cctv_homepage":
                records.extend(parse_cctv_homepage(payload, src["name"], src["url"]))
            elif src["type"] == "rss":
                records.extend(parse_rss(payload, src["name"]))
        except Exception as exc:
            errors.append(f"{src['name']}: {exc}")

    deduped = {}
    for record in records:
        key = record["dedupe_key"]
        if key not in deduped:
            deduped[key] = record
        elif record.get("published_at", "") > deduped[key].get("published_at", ""):
            deduped[key] = record
    return sorted(deduped.values(), key=lambda item: item.get("published_at", "") or item["observed_at"], reverse=True), errors


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


def digest_label(now, requested):
    if requested == "morning":
        return "晨间新闻"
    if requested == "evening":
        return "晚间新闻"
    return "晨间新闻" if now.hour < 12 else "晚间新闻"


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def build_markdown(now, label, records, errors, report_path, lookback_hours):
    start = now - timedelta(hours=lookback_hours)
    lines = [
        f"**Window:** {start.strftime('%Y-%m-%d %H:%M')}-{now.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai",
        f"**Digest:** {label}",
        f"**主要来源：** 央视新闻 (news.cctv.com)，辅以 CGTN 英文 RSS",
        f"**Report file:** `{report_path}`",
        "",
        "**重点摘要**",
    ]
    for item in records[:8]:
        lines.append(f"- [{item['topic_label']} / 影响：{item['impact_level']}] {item['summary']}")
    if not records:
        lines.append("- 本轮没有抓取到可用新闻。")

    lines.extend(["", "**新闻详情**"])
    for index, item in enumerate(records, start=1):
        body_text = item.get("text_excerpt", item.get("description", ""))
        lines.extend([
            "",
            f"### {index}. {item['topic_label']}（影响：{item['impact_level']}）",
            f"- **来源：** {item['source']}",
            f"- **标题：** {item['summary']}",
            f"- **原文内容：**",
            f"",
            f"  {body_text}",
            f"",
            f"- **分析：** {item['chinese_description']}",
            f"- **可能影响：** {item['impact']}",
            f"- **链接：** {item['content_url']}",
        ])

    lines.extend([
        "",
        "**来源说明**",
        "- 央视新闻：采集 news.cctv.com 首页公开文章链接，抓取原文内容。",
        "- CGTN：使用官方 RSS 作为英文补充来源。",
        "- 本脚本只读取公开网页和 RSS，不绕过登录、付费墙、反爬或隐私限制。",
    ])
    if errors:
        lines.append("- 来源错误：" + "; ".join(errors))
    return "\n".join(lines) + "\n"


def build_html_body(now, label, records, errors, report_path):
    cards = []
    for item in records[:10]:
        body_text = item.get("text_excerpt", item.get("description", ""))
        level_color = "#dc2626" if item["impact_level"] == "高" else "#b45309" if item["impact_level"] == "中" else "#4b5563"
        cards.append(
            "<div style='border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:12px 0;background:#ffffff;'>"
            f"<div style='font-size:13px;line-height:20px;color:#6b7280;'>{html.escape(item['source'])}</div>"
            "<div style='margin-top:8px;'>"
            f"<span style='display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:700;'>{html.escape(item['topic_label'])}</span>"
            f"<span style='display:inline-block;margin-left:6px;color:{level_color};font-size:12px;font-weight:700;'>影响：{html.escape(item['impact_level'])}</span>"
            "</div>"
            f"<h3 style='font-size:17px;line-height:26px;color:#111827;margin:12px 0 6px 0;'>{html.escape(item['summary'])}</h3>"
            "<div style='background:#fefce8;border-left:3px solid #eab308;padding:10px 14px;border-radius:4px;margin:10px 0;'>"
            "<div style='font-size:12px;color:#92400e;font-weight:700;margin-bottom:4px;'>CHINESE (原文)</div>"
            f"<div style='font-size:14px;line-height:24px;color:#422006;white-space:pre-wrap;'>{html.escape(body_text[:800])}</div>"
            "</div>"
            f"<p style='font-size:14px;line-height:22px;color:#374151;margin:8px 0 0 0;'><strong>分析：</strong>{html.escape(item['chinese_description'])}</p>"
            f"<p style='font-size:14px;line-height:22px;color:#374151;margin:6px 0 0 0;'><strong>可能影响：</strong>{html.escape(item['impact'])}</p>"
            f"<div style='margin-top:8px;font-size:13px;line-height:20px;'><a href='{html.escape(item['content_url'])}' style='color:#2563eb;'>查看原文</a></div>"
            "</div>"
        )
    if not cards:
        cards.append("<div style='padding:12px;color:#374151;'>本轮没有抓取到可用新闻。</div>")
    error_note = f"<p style='color:#b45309;'>来源错误：{html.escape('; '.join(errors))}</p>" if errors else ""
    return f"""<!doctype html>
<html>
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,'PingFang SC','Microsoft YaHei',sans-serif;color:#111827;background:#f3f4f6;margin:0;padding:24px;">
    <div style="max-width:820px;margin:0 auto;">
      <div style="background:#cc0000;border-radius:14px 14px 0 0;padding:22px 24px;">
        <div style="font-size:13px;color:#ffcccc;">央视新闻 · CGTN</div>
        <h1 style="font-size:25px;line-height:34px;margin:6px 0 8px 0;color:#ffffff;">{html.escape(label)}摘要</h1>
        <p style="color:#ffd4d4;margin:0;">{now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai · 共 {len(records)} 条</p>
      </div>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 14px 14px;padding:18px 20px;">
        <p style="font-size:14px;line-height:22px;color:#374151;margin:0 0 12px 0;">主要来源为央视新闻（news.cctv.com），辅以 CGTN 英文 RSS。每条新闻包含原文内容与分析。完整 Markdown 报告已作为附件发送：<code>{html.escape(str(report_path))}</code></p>
        {''.join(cards)}
        <div style="border-top:1px solid #e5e7eb;margin-top:16px;padding-top:12px;color:#6b7280;font-size:13px;line-height:20px;">
          主要来源：央视新闻 (news.cctv.com) + CGTN 官方 RSS。只读取公开网页，不绕过登录、付费墙或反爬限制。
        </div>
        {error_note}
      </div>
    </div>
  </body>
</html>"""


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
        subject = f"{label}摘要 · 央视新闻 · {now.strftime('%Y-%m-%d %H:%M')}"
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
