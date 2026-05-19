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
from tweet_fetcher import fetch_tweets


HOME = Path.home()
TARGET = "Elon Musk"
TARGET_HANDLE = "@elonmusk"
TZ = ZoneInfo(os.environ.get("ELON_MONITOR_TIMEZONE", "Asia/Shanghai"))
BASE_DIR = Path(os.environ.get("ELON_MONITOR_DIR", str(HOME / ".codex" / "monitoring" / "elon-musk"))).expanduser()
REPORT_DIR = BASE_DIR / "reports"
STATE_DIR = BASE_DIR / "state"
RUN_LOG = BASE_DIR / "runs.jsonl"
SEEN_FILE = STATE_DIR / "seen-keys.json"
TEXT_LOG = HOME / ".codex" / "log" / "elon-musk-media-monitor.log"
NODE_BIN = os.environ.get("ELON_MONITOR_NODE_BIN") or shutil.which("node") or "/usr/local/bin/node"
SEND_EMAIL_SCRIPT = Path(
    os.environ.get(
        "ELON_MONITOR_SEND_EMAIL_SCRIPT",
        str(Path(__file__).resolve().with_name("send_email_with_attachment_via_email_mcp.mjs")),
    )
).expanduser()
EMAIL_ACCOUNT = os.environ.get("ELON_MONITOR_EMAIL_ACCOUNT", "1982549567@qq.com")
EMAIL_TO = os.environ.get("ELON_MONITOR_EMAIL_TO", EMAIL_ACCOUNT)
FETCH_PROXY = os.environ.get("ELON_MONITOR_PROXY") or os.environ.get("MONITOR_PROXY") or ""


def parse_args():
    parser = argparse.ArgumentParser(description="Monitor public media updates related to Elon Musk.")
    parser.add_argument("--dry-run", action="store_true", help="Generate a report without sending email or updating seen state.")
    parser.add_argument("--force-email", action="store_true", help="Send email even when there are no new items.")
    parser.add_argument("--lookback-hours", type=int, default=24, help="RSS query window in hours.")
    parser.add_argument("--max-items", type=int, default=12, help="Maximum items to include in the digest.")
    return parser.parse_args()


def append_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def load_seen():
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_title(title, source):
    title = clean_text(title)
    source = clean_text(source)
    if source and title.lower().endswith(f" - {source}".lower()):
        title = title[: -(len(source) + 3)].strip()
    return title


def key_for(title):
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def classify(title):
    lowered = title.lower()
    tags = []
    if any(term in lowered for term in ["openai", "sam altman", "xai", "grok", "ai "]):
        tags.append("ai")
    if any(term in lowered for term in ["tesla", "cybertruck"]) or re.search(r"\bevs?\b|\belectric vehicle\b", lowered):
        tags.append("tesla")
    if any(term in lowered for term in ["spacex", "starlink", "rocket"]):
        tags.append("spacex")
    if any(term in lowered for term in ["x ", "twitter", "social media"]):
        tags.append("x")
    if any(term in lowered for term in ["china", "trump", "trial", "lawsuit", "court"]):
        tags.append("public-affairs")
    return tags or ["media"]


def chinese_brief(title, source):
    lowered = title.lower()
    source_label = source or "公开媒体"

    if any(term in lowered for term in ["openai", "sam altman", "trial", "lawsuit", "jury", "court"]):
        return {
            "topic_label": "AI / 诉讼",
            "impact_level": "高",
            "chinese_description": (
                f"{source_label} 报道了马斯克与 OpenAI、Sam Altman 相关诉讼或庭审进展。"
                "这类信息主要反映双方围绕 OpenAI 治理、控制权、非营利定位和商业化路线的争议。"
            ),
            "impact": (
                "可能影响外界对 OpenAI 治理结构和 xAI 竞争叙事的判断；若出现关键判决或陪审团结论，"
                "还可能带动 AI 公司监管、投资人信心和行业舆论变化。"
            ),
        }

    if (
        any(term in lowered for term in ["china", "trump", "state banquet", "beijing", "premier"])
        or re.search(r"\bxi\s+(jinping|tells|meets)\b", lowered)
    ):
        return {
            "topic_label": "中国行 / 政商关系",
            "impact_level": "高",
            "chinese_description": (
                f"{source_label} 关注马斯克出现在中国相关外交、企业家会见或国宴场景。"
                "这通常与 Tesla 中国业务、供应链关系、监管沟通和美中商业往来有关。"
            ),
            "impact": (
                "可能影响市场对 Tesla 中国业务稳定性、政策沟通能力和供应链风险的预期；"
                "若与高层会见或贸易议题绑定，影响会偏向品牌、地缘政治和资本市场情绪。"
            ),
        }

    if any(term in lowered for term in ["tesla", "cybertruck"]) or re.search(r"\bevs?\b|\belectric vehicle\b", lowered):
        return {
            "topic_label": "Tesla / 电动车",
            "impact_level": "中",
            "chinese_description": (
                f"{source_label} 的报道与 Tesla、电动车竞争、产品或马斯克作为汽车公司领导者的公开动态有关。"
            ),
            "impact": (
                "可能影响 Tesla 品牌声量、消费者预期和投资者对需求或竞争格局的判断；"
                "如果涉及产品安全、交付或竞争对手选择，影响会更偏业务基本面。"
            ),
        }

    if any(term in lowered for term in ["spacex", "starlink", "rocket", "delta", "amazon leo"]):
        return {
            "topic_label": "SpaceX / Starlink",
            "impact_level": "中",
            "chinese_description": (
                f"{source_label} 报道了 SpaceX、Starlink 或卫星互联网相关商业竞争。"
                "这类新闻通常体现 Starlink 在航空、通信或政府市场的拓展与阻力。"
            ),
            "impact": (
                "可能影响外界对 Starlink 商业化速度、企业客户接受度和与 Amazon 等竞争方关系的判断；"
                "短期更多是舆论和订单预期，长期取决于实际合同。"
            ),
        }

    if any(term in lowered for term in ["xai", "grok", "coding agent"]):
        return {
            "topic_label": "xAI / 产品",
            "impact_level": "中",
            "chinese_description": (
                f"{source_label} 关注 xAI 或 Grok 相关产品进展，尤其是面向开发者、编程或 AI 助手能力的发布。"
            ),
            "impact": (
                "可能提升 xAI 与 OpenAI、Anthropic 等公司的竞争可见度；若产品体验强，"
                "会影响开发者生态和企业试用兴趣。"
            ),
        }

    if any(term in lowered for term in ["x ", "twitter", "history feature", "social media"]):
        return {
            "topic_label": "X / 社交平台",
            "impact_level": "中",
            "chinese_description": (
                f"{source_label} 报道了 X 平台功能、运营或马斯克围绕社交媒体平台的动作。"
            ),
            "impact": (
                "可能影响 X 的用户体验、内容分发和广告主信心；功能级更新通常影响有限，"
                "但若牵涉隐私、监管或商业化策略则更值得关注。"
            ),
        }

    if any(term in lowered for term in ["bitcoin", "wealth", "saylor"]):
        return {
            "topic_label": "财富 / 加密资产",
            "impact_level": "低",
            "chinese_description": (
                f"{source_label} 将马斯克个人财富、加密资产或其他富豪比较作为报道角度。"
            ),
            "impact": (
                "这类内容更多影响公众话题热度，对马斯克旗下公司的直接经营影响较弱；"
                "除非与 Tesla 持仓、资本运作或重大投资决策相连。"
            ),
        }

    if any(term in lowered for term in ["odyssey", "actress", "casting", "whoopi", "view"]):
        return {
            "topic_label": "文化争议 / 舆论",
            "impact_level": "低",
            "chinese_description": (
                f"{source_label} 报道了马斯克对影视、文化或公众人物议题的表态引发的讨论。"
            ),
            "impact": (
                "主要影响个人舆论形象和社交平台讨论热度，对核心业务影响通常较低；"
                "但持续争议可能间接影响品牌好感度。"
            ),
        }

    return {
        "topic_label": "综合媒体动态",
        "impact_level": "低",
        "chinese_description": (
            f"{source_label} 发布了与马斯克相关的公开报道。建议结合原文判断其与 Tesla、SpaceX、xAI 或 X 的实际关联。"
        ),
        "impact": (
            "当前更像一般媒体曝光，直接业务影响不明确；若后续被主流媒体持续跟进，"
            "再观察是否升级为市场、监管或品牌层面的事件。"
        ),
    }


def google_news_url(query, lookback_hours):
    when = "1d" if lookback_hours <= 24 else f"{max(1, round(lookback_hours / 24))}d"
    q = f"{query} when:{when}"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "zh-CN", "gl": "US", "ceid": "US:en"}
    )


def fetch_url(url):
    return resilient_fetch_url(url, user_agent="Codex social-monitoring personal RSS reader/1.0", proxy=FETCH_PROXY or None)


def extract_rss_description(item):
    desc = clean_text(item.findtext("description", ""))
    if not desc:
        return ""
    desc = re.sub(r"<(a|img)[^>]*>.*?</\1>", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<br\s*/?>", "\n", desc, flags=re.IGNORECASE)
    desc = re.sub(r"</?(p|div|li|ol|ul|span|b|i|em|strong|font)[^>]*>", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"&nbsp;", " ", desc)
    desc = re.sub(r"\n{3,}", "\n\n", desc)
    desc = re.sub(r" +", " ", desc)
    desc = re.sub(r"\n +", "\n", desc)
    lines = [line.strip() for line in desc.split("\n")]
    desc = "\n".join(line for line in lines if line)
    return desc.strip()


def parse_rss(xml_bytes, retrieval_method):
    root = ET.fromstring(xml_bytes)
    records = []
    for item in root.findall(".//item"):
        source_node = item.find("source")
        source = clean_text(source_node.text if source_node is not None else "")
        source_url = source_node.attrib.get("url") if source_node is not None else ""
        title = normalize_title(item.findtext("title", ""), source)
        link = clean_text(item.findtext("link", ""))
        guid = clean_text(item.findtext("guid", ""))
        pub_raw = clean_text(item.findtext("pubDate", ""))
        description = extract_rss_description(item)
        try:
            published = email.utils.parsedate_to_datetime(pub_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=ZoneInfo("UTC"))
        except (TypeError, ValueError):
            published = None
        if not title or not link:
            continue
        brief = chinese_brief(title, source)
        text_excerpt = description if description else title
        records.append(
            {
                "target": "elon-musk",
                "platform": "public-web",
                "record_type": "mention",
                "author_handle": "",
                "author_url": source_url,
                "content_url": link,
                "platform_id": guid or link,
                "published_at": published.isoformat() if published else "",
                "published_display": published.astimezone(TZ).strftime("%Y-%m-%d %H:%M") if published else "",
                "observed_at": datetime.now(TZ).isoformat(timespec="seconds"),
                "source": source or "Unknown source",
                "text_excerpt": text_excerpt,
                "summary": title,
                "topic_label": brief["topic_label"],
                "chinese_description": brief["chinese_description"],
                "impact": brief["impact"],
                "impact_level": brief["impact_level"],
                "tags": classify(title),
                "retrieval_method": retrieval_method,
                "confidence": "medium",
                "dedupe_key": key_for(title),
            }
        )
    return records


def collect_records(lookback_hours):
    queries = [
        '"Elon Musk"',
        '"Elon Musk" (Tesla OR SpaceX OR Starlink OR xAI OR OpenAI OR X)',
    ]
    records = []
    errors = []
    for query in queries:
        url = google_news_url(query, lookback_hours)
        try:
            records.extend(parse_rss(fetch_url(url), f"google-news-rss:{query}"))
        except Exception as exc:
            errors.append(f"{query}: {exc}")

    deduped = {}
    for record in records:
        current = deduped.get(record["dedupe_key"])
        if current is None:
            deduped[record["dedupe_key"]] = record
            continue
        if record.get("published_at", "") > current.get("published_at", ""):
            deduped[record["dedupe_key"]] = record

    return sorted(deduped.values(), key=lambda item: item.get("published_at", ""), reverse=True), errors


def collect_tweets():
    """Fetch recent tweets from @elonmusk via Nitter RSS."""
    try:
        tweets = fetch_tweets("elonmusk", proxy=FETCH_PROXY or None)
    except Exception as exc:
        return [], [f"tweets: {exc}"]
    for t in tweets:
        t["target"] = "elon-musk"
        t["topic_label"] = "推文 / 转发" if t["is_retweet"] else "推文 / 原创"
        t["impact_level"] = "中"
        t["chinese_description"] = _tweet_chinese_brief(t)
        t["impact"] = (
            "马斯克在社交平台上的直接发声，常常快速改变媒体议程并影响其旗下公司"
            "（Tesla、SpaceX、xAI、X）的舆论走向和投资者情绪。"
        )
        t["source"] = f"X/Twitter · {t['original_author']}"
        t["tags"] = ["social-platform"]
        t["confidence"] = "high"
    return tweets, []


def _tweet_chinese_brief(tweet):
    prefix = "转发" if tweet["is_retweet"] else "发推"
    text = tweet["summary"]
    if len(text) > 200:
        text = text[:197] + "..."
    return f"马斯克在 X/Twitter {prefix}：「{text}」"


def build_markdown(now, records, new_records, errors, report_path, tweets=None, new_tweets=None):
    tweets = tweets or []
    new_tweets = new_tweets or []
    start = now - timedelta(hours=24)
    lines = [
        f"**Window:** {start.strftime('%Y-%m-%d %H:%M')}-{now.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai",
        f"**Target:** {TARGET} / {TARGET_HANDLE}",
        f"**Report file:** `{report_path}`",
        "",
        "**中文摘要**",
    ]
    highlights = new_tweets[:3] + (new_records[:3] or records[:3])
    if highlights:
        for item in highlights[:6]:
            label = "新增" if (item in new_records or item in new_tweets) else "已收录"
            lines.append(
                f"- [{label}] {item['topic_label']}：{item['chinese_description']} "
                f"可能影响：{item['impact']}"
            )
    else:
        lines.append("- 本轮没有抓取到新的公开网页/新闻候选项。")

    # Tweet section
    if tweets:
        lines.extend(["", "**🪽 X/Twitter 推文原文**", ""])
        for index, item in enumerate(tweets[:15], start=1):
            rt_label = " [转发]" if item.get("is_retweet") else ""
            lines.extend([
                f"### 推文 {index}.{rt_label}",
                f"- **时间：** {item['published_display'] or '-'} · @{item.get('original_author', '')}",
                f"- **原文 (English)：**",
                f"  > {item['text_excerpt']}",
                f"- **中文摘要：** {item['chinese_description']}",
                f"- **链接：** {item['content_url']}",
                "",
            ])
    else:
        lines.extend([
            "",
            "**🪽 X/Twitter 推文原文**",
            "- 本轮未获取到推文（Nitter 源可能受限或账号暂无新推文）。",
            "",
        ])

    lines.extend(["**相关媒体动态**", ""])
    for index, item in enumerate((new_records or records)[:12], start=1):
        excerpt = item.get("text_excerpt", item["summary"])
        lines.extend(
            [
                f"### {index}. {item['topic_label']}（影响：{item['impact_level']}）",
                f"- **时间/来源：** {item['published_display'] or '-'} · {item['source']}",
                f"- **标题：** {item['summary']}",
                f"- **原文内容 (English)：**",
                f"  > {excerpt}",
                f"- **中文分析：** {item['chinese_description']}",
                f"- **可能影响：** {item['impact']}",
                f"- **链接：** {item['content_url']}",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "**Gaps**",
            "- X/Twitter 直接发帖监控需要官方 X API；当前不会抓取或绕过登录、反爬和隐私控制。",
            "- Instagram/Facebook 公共内容覆盖需要合规的 Meta 访问权限；当前未启用。",
            "- Google News RSS 只作为公开网页线索来源；重要判断仍建议打开原文链接确认上下文。",
        ]
    )
    if errors:
        lines.append("- 来源错误：" + "; ".join(errors))
    return "\n".join(lines) + "\n"


def build_html_body(now, records, new_records, report_path, errors, tweets=None, new_tweets=None):
    tweets = tweets or []
    new_tweets = new_tweets or []
    selected = new_records[:6] or records[:6]

    # Tweet cards first (blue style)
    tweet_cards = []
    for item in tweets[:8]:
        rt_badge = ' <span style="display:inline-block;background:#fef3c7;color:#92400e;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700;margin-left:4px;">转发</span>' if item.get("is_retweet") else ""
        tweet_cards.append(
            "<div style='border:1px solid #bae6fd;border-radius:10px;padding:14px 16px;margin:12px 0;background:#f0f9ff;'>"
            "<div style='font-size:13px;line-height:20px;color:#0369a1;'>"
            f"🪽 {html.escape(item['published_display'] or '-')} · @{html.escape(item.get('original_author', ''))}{rt_badge}"
            "</div>"
            "<div style='margin-top:10px;background:#ffffff;border-radius:8px;padding:12px 14px;'>"
            "<div style='font-size:12px;color:#6b7280;font-weight:700;margin-bottom:6px;'>ENGLISH (原文)</div>"
            f"<div style='font-size:15px;line-height:24px;color:#111827;white-space:pre-wrap;'>{html.escape(item['text_excerpt'])}</div>"
            "</div>"
            f"<p style='font-size:14px;line-height:22px;color:#075985;margin:10px 0 0 0;'><strong>中文：</strong>{html.escape(item['chinese_description'])}</p>"
            f"<div style='margin-top:8px;font-size:13px;line-height:20px;'><a href='{html.escape(item['content_url'])}' style='color:#0284c7;'>查看原推</a></div>"
            "</div>"
        )
    if not tweet_cards:
        tweet_cards.append("<div style='padding:12px;color:#6b7280;font-size:13px;'>本轮未获取到推文（Nitter 源可能受限或账号暂无新推文）。</div>")

    # News cards
    cards = []
    for item in selected:
        excerpt = item.get("text_excerpt", item["summary"])
        level_color = "#dc2626" if item["impact_level"] == "高" else "#b45309" if item["impact_level"] == "中" else "#4b5563"
        cards.append(
            "<div style='border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:12px 0;background:#ffffff;'>"
            "<div style='font-size:13px;line-height:20px;color:#6b7280;'>"
            f"{html.escape(item['published_display'] or '-')} · {html.escape(item['source'])}"
            "</div>"
            "<div style='margin-top:8px;'>"
            f"<span style='display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:700;'>{html.escape(item['topic_label'])}</span>"
            f"<span style='display:inline-block;margin-left:6px;color:{level_color};font-size:12px;font-weight:700;'>影响：{html.escape(item['impact_level'])}</span>"
            "</div>"
            f"<p style='font-size:15px;line-height:24px;color:#111827;margin:10px 0 0 0;'><strong>标题：</strong>{html.escape(item['summary'])}</p>"
            "<div style='margin-top:10px;background:#f0f9ff;border-left:3px solid #0ea5e9;padding:10px 14px;border-radius:4px;'>"
            "<div style='font-size:12px;color:#0369a1;font-weight:700;margin-bottom:4px;'>ENGLISH (原文)</div>"
            f"<div style='font-size:14px;line-height:22px;color:#0c4a6e;white-space:pre-wrap;'>{html.escape(excerpt)}</div>"
            "</div>"
            f"<p style='font-size:15px;line-height:24px;color:#111827;margin:10px 0 0 0;'><strong>中文分析：</strong>{html.escape(item['chinese_description'])}</p>"
            f"<p style='font-size:15px;line-height:24px;color:#374151;margin:8px 0 0 0;'><strong>可能影响：</strong>{html.escape(item['impact'])}</p>"
            f"<div style='margin-top:8px;font-size:13px;line-height:20px;'><a href='{html.escape(item['content_url'])}' style='color:#2563eb;'>查看来源</a></div>"
            "</div>"
        )
    if not cards:
        cards.append("<div style='padding:12px;color:#374151;'>本轮没有抓取到公开网页/新闻候选项。</div>")
    error_note = ""
    if errors:
        error_note = f"<p style='color:#b45309;'>错误：{html.escape('; '.join(errors))}</p>"
    return f"""<!doctype html>
<html>
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,'PingFang SC','Microsoft YaHei',sans-serif;color:#111827;background:#f3f4f6;margin:0;padding:24px;">
    <div style="max-width:780px;margin:0 auto;">
      <div style="background:#111827;border-radius:14px 14px 0 0;padding:22px 24px;">
        <div style="font-size:13px;color:#9ca3af;">Social Monitoring</div>
        <h1 style="font-size:25px;line-height:34px;margin:6px 0 8px 0;color:#ffffff;">马斯克公开媒体动态简报</h1>
        <p style="color:#d1d5db;margin:0;">{now.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai · 推文 {len(tweets)} 条 · 新闻新增 {len(new_records)} 条 · 候选 {len(records)} 条</p>
      </div>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 14px 14px;padding:18px 20px;">
        <p style="font-size:14px;line-height:22px;color:#374151;margin:0 0 12px 0;">Markdown 完整报告已作为附件发送：<code>{html.escape(str(report_path))}</code></p>
        <h2 style="font-size:18px;color:#0369a1;margin:20px 0 10px 0;">🪽 X/Twitter 推文原文</h2>
        {''.join(tweet_cards)}
        <h2 style="font-size:18px;color:#111827;margin:24px 0 10px 0;">📰 相关媒体报道</h2>
        {''.join(cards)}
        <div style="border-top:1px solid #e5e7eb;margin-top:16px;padding-top:12px;color:#6b7280;font-size:13px;line-height:20px;">
          X/Twitter 推文通过 Nitter RSS 公开源获取。
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
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_LOG.parent.mkdir(parents=True, exist_ok=True)

    records, news_errors = collect_records(args.lookback_hours)
    records = records[: max(args.max_items, 1)]
    tweets, tweet_errors = collect_tweets()
    errors = news_errors + tweet_errors

    seen = load_seen()
    new_records = [item for item in records if item["dedupe_key"] not in seen]
    new_tweets = [item for item in tweets if item["dedupe_key"] not in seen]

    report_path = REPORT_DIR / f"elon-musk-media-{now.strftime('%Y%m%d-%H%M%S')}.md"
    markdown = build_markdown(now, records, new_records, errors, report_path, tweets, new_tweets)
    report_path.write_text(markdown, encoding="utf-8")

    email_sent = False
    email_result = ""
    try:
        if not args.dry_run and (new_records or new_tweets or args.force_email or not seen):
            total_new = len(new_tweets) + len(new_records)
            subject = f"马斯克媒体动态简报 · 推文 {len(new_tweets)} 条 · 新闻 {len(new_records)} 条 · {now.strftime('%Y-%m-%d %H:%M')}"
            html_body = build_html_body(now, records, new_records, report_path, errors, tweets, new_tweets)
            email_result = send_email(subject, html_body, report_path)
            email_sent = True
    finally:
        if not args.dry_run:
            seen.update(item["dedupe_key"] for item in records)
            seen.update(item["dedupe_key"] for item in tweets)
            save_seen(seen)

    run_record = {
        "timestamp": now.isoformat(timespec="seconds"),
        "records": len(records),
        "newRecords": len(new_records),
        "tweets": len(tweets),
        "newTweets": len(new_tweets),
        "emailSent": email_sent,
        "emailResult": email_result,
        "reportPath": str(report_path),
        "errors": errors,
        "dryRun": args.dry_run,
    }
    append_text(RUN_LOG, json.dumps(run_record, ensure_ascii=False, separators=(",", ":")))
    append_text(
        TEXT_LOG,
        f"[{run_record['timestamp']}] records={len(records)} new={len(new_records)} tweets={len(tweets)} newTweets={len(new_tweets)} emailSent={email_sent} report={report_path}",
    )
    print(json.dumps(run_record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
