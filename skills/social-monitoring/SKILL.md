---
name: social-monitoring
description: Monitor public social-media activity for target people, organizations, or accounts across X/Twitter, Instagram, Facebook, and public web sources. Use when the user asks to track a target's posts, tweets, public updates, mentions, related events, daily digests, alerts, or cross-platform source search, while respecting platform access rules and avoiding private or unauthorized content.
---

# Social Monitoring

## Overview

Use this skill to build evidence-backed monitoring reports for public social activity around a target account or public figure. It prioritizes official APIs and public sources, preserves links and timestamps, and produces concise daily or event-driven digests.

Do not bypass logins, rate limits, robots controls, paywalls, privacy settings, or platform access restrictions. If the request requires private posts, DMs, closed groups, hidden stories, or unauthorized scraping, explain the boundary and offer a public-source alternative.

For platform-specific access notes and source links, read `references/platform-access.md`.

## Intake

Before running or designing a monitor, identify:

- Target: canonical person/org name plus known handles, aliases, and official URLs.
- Platforms: X/Twitter, Instagram, Facebook, Threads, YouTube, public web, or a narrower list.
- Time window: today, yesterday, since last run, or explicit date range with timezone.
- Output: brief digest, full evidence table, alert, JSONL archive, spreadsheet, or email/slack-ready summary.
- Access: available API keys, browser session, official dataset access, or public web search only.

If a reasonable default is needed, use the user's timezone when known, a daily window from `00:00` to `23:59`, and only public posts from official or strongly verified accounts.

## Source Priority

Use sources in this order:

1. Official platform API or platform-provided public-content tool.
2. Verified public profile pages and permanent post URLs.
3. Reliable news or archival sources that quote or embed the target's posts.
4. General web search results only as leads; verify them against a stable URL before reporting.

For each item, keep the evidence URL, platform, author handle, post id or URL, observed timestamp, published timestamp, and retrieval method. Mark uncertain identity matches instead of silently merging them.

## Workflow

1. Resolve identity:
   - Map each target to known handles and canonical profile URLs.
   - Prefer verified accounts, official websites, campaign/company pages, or existing user-provided handles.
   - Treat parody, fan, repost, and impersonation accounts as separate sources.

2. Collect public activity:
   - Pull direct target posts first.
   - Then search platform/public web mentions of the target, only if the user asked for events, reactions, or wider context.
   - Preserve original text only as short excerpts; summarize long posts and articles.

3. Normalize records:
   - Use one record per platform post, story-equivalent public item, article, or event.
   - Dedupe by platform post id first, then canonical URL, then author/time/text similarity.
   - Convert times to the requested timezone while keeping original timestamps when available.

4. Classify:
   - `direct-post`: authored by the target account.
   - `reply-or-comment`: authored by the target in response to another item.
   - `reshare-or-quote`: amplified by the target.
   - `mention`: public content about the target.
   - `event`: an offline or newsworthy event connected to the target.

5. Report:
   - Lead with the most important new direct posts and events.
   - Include source links beside every claim.
   - Separate confirmed items from weak or unverified leads.
   - Note API gaps, inaccessible platforms, and rate-limit or permission limits.

## Daily Digest Shape

Use this structure unless the user requests another format:

```markdown
**Window:** 2026-05-14 00:00-23:59 Asia/Shanghai
**Target:** Donald Trump / @realDonaldTrump

**Highlights**
- ...

**Direct Posts**
| Time | Platform | Account | Summary | Link |
|---|---|---|---|---|

**Related Events & Mentions**
| Time | Source | Type | Summary | Link |
|---|---|---|---|---|

**Gaps**
- ...
```

## Data Model

When creating an archive, use JSONL with stable keys:

```json
{
  "target": "elon-musk",
  "platform": "x",
  "record_type": "direct-post",
  "author_handle": "elonmusk",
  "author_url": "https://x.com/elonmusk",
  "content_url": "https://x.com/elonmusk/status/...",
  "platform_id": "...",
  "published_at": "2026-05-14T12:34:56Z",
  "observed_at": "2026-05-14T13:00:00+08:00",
  "text_excerpt": "...",
  "summary": "...",
  "tags": ["policy", "business"],
  "retrieval_method": "official-api",
  "confidence": "high"
}
```

## Monitoring Setup Guidance

For a scheduled monitor, keep the skill implementation separate from secrets and live state:

- Store API keys in environment variables, keychain, `.env` files excluded from git, or the user's existing secret manager.
- Store seen-post ids in JSONL, SQLite, or a spreadsheet so repeated runs only alert on new records.
- Prefer incremental queries using since ids, cursors, timestamps, or the last successful run time.
- Log source failures per platform instead of failing the whole report.
- Ask before sending externally visible alerts, emails, or messages.

## Examples

- "用 `$social-monitoring` 监控川普今天在 X、Facebook、Instagram 的公开发帖和相关事件，输出中文日报。"
- "Use `$social-monitoring` to track Elon Musk's new X posts since yesterday and list only market-moving items with links."
- "用 `$social-monitoring` 帮我设计一个每天早上 9 点生成马斯克跨平台公开动态摘要的本地监控流程。"
