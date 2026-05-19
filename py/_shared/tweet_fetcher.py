#!/usr/bin/env python3
"""Fetch tweets via Nitter RSS (no API key required)."""
import email.utils
import hashlib
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

from net_fetch import fetch_url as resilient_fetch_url


def _clean(text):
    value = html.unescape(text or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _clean_description(raw):
    """Extract readable text from Nitter RSS description HTML."""
    if not raw:
        return ""
    text = raw
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<hr\s*/?>", "\n---\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(blockquote|footer|cite)[^>]*>.*?</\1>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(a|img)[^>]*>.*?</\1>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&apos;", "'", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n +", "\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def nitter_rss_url(handle, mode="with_replies"):
    """Build Nitter RSS URL for a Twitter handle."""
    encoded = urllib.parse.quote(handle.lstrip("@"))
    return f"https://nitter.net/{encoded}/rss"


def key_for(text):
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def fetch_tweets(handle, proxy=None, user_agent="Codex social-monitoring tweet reader/1.0", timeout=30):
    """Fetch recent tweets for a handle via Nitter RSS.

    Returns list of tweet dicts:
        target, platform, record_type, author_handle, original_author,
        content_url, tweet_id, published_at, published_display, observed_at,
        text_excerpt, summary, is_retweet, dedupe_key
    """
    url = nitter_rss_url(handle)
    xml_bytes = resilient_fetch_url(url, user_agent=user_agent, timeout=timeout, proxy=proxy)
    root = ET.fromstring(xml_bytes)

    tweets = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title", ""))
        creator = _clean(item.findtext("{http://purl.org/dc/elements/1.1/}creator", ""))
        if not creator:
            creator = _clean(item.findtext("dc:creator", ""))
        description_raw = item.findtext("description", "")
        description = _clean_description(description_raw) if description_raw else ""
        link = _clean(item.findtext("link", ""))
        guid = _clean(item.findtext("guid", ""))
        pub_raw = _clean(item.findtext("pubDate", ""))

        if not title or not guid:
            continue

        # Determine if this is a retweet
        is_retweet = False
        tweet_text = title
        original_author = creator.lstrip("@")
        if title.startswith("RT by "):
            is_retweet = True
            match = re.match(r"^RT by @\w+:\s*(.*)", title)
            tweet_text = match.group(1) if match else title
        elif title.startswith("Pinned:"):
            tweet_text = title.replace("Pinned:", "").strip()

        # Use description as text_excerpt, strip media-only noise
        text_excerpt = description if len(description) > len(tweet_text) else tweet_text
        if not text_excerpt or len(text_excerpt) < 3:
            text_excerpt = tweet_text
        # Clean up trailing "Video" / "Photo" noise from description extraction
        text_excerpt = re.sub(r"\n(Video|Photo|Image)\s*$", "", text_excerpt).strip()
        if text_excerpt.lower() in ("video", "photo", "image"):
            text_excerpt = tweet_text

        try:
            published = email.utils.parsedate_to_datetime(pub_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=ZoneInfo("UTC"))
        except (TypeError, ValueError):
            published = None

        # Build x.com URL from tweet ID
        tweet_id = guid
        x_url = f"https://x.com/{original_author}/status/{tweet_id}"

        tweets.append({
            "target": "",
            "platform": "x-twitter",
            "record_type": "retweet" if is_retweet else "tweet",
            "author_handle": handle if not handle.startswith("@") else handle,
            "original_author": original_author,
            "content_url": x_url,
            "nitter_url": link,
            "tweet_id": tweet_id,
            "published_at": published.isoformat() if published else "",
            "published_display": published.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M") if published else "",
            "observed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "text_excerpt": text_excerpt,
            "summary": tweet_text,
            "is_retweet": is_retweet,
            "dedupe_key": key_for(tweet_id),
        })

    return tweets
