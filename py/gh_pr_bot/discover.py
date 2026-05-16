#!/usr/bin/env python3
"""Discover repos and issues from GitHub."""
import json
import subprocess
import time
import sys
from pathlib import Path
from typing import Union
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))

from config import (
    MIN_STARS, MAX_STARS, RECENCY_DATE, LANGUAGES,
    TARGET_LABELS, FIXABLE_TITLE_KW, HARD_TITLE_KW,
    SEARCH_EXCLUDE_TOPICS, TARGET_LABELS,
)
from state_manager import StateManager


def _gh_api(endpoint: str, timeout: int = 120) -> Union[dict, list]:
    """Call gh api and return parsed JSON."""
    args = ["gh", "api", endpoint]
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {endpoint}: {r.stderr.strip()}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {}


def _gh_api_text(endpoint: str) -> str:
    """Call gh api and return raw text."""
    args = ["gh", "api", endpoint]
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {endpoint}: {r.stderr.strip()}")
    return r.stdout.strip()


def search_repos(state: StateManager, max_pages: int = 3) -> list:
    """Search GitHub for TS/JS repos in target star range with good-first-issues."""
    repos = []

    for lang in LANGUAGES:
        for page in range(1, max_pages + 1):
            if len(repos) >= 30:
                break
            q = f"stars:{MIN_STARS}..{MAX_STARS}+language:{lang}+pushed:>{RECENCY_DATE}"
            try:
                data = _gh_api(f"search/repositories?q={q}&sort=updated&per_page=30&page={page}")
                items = data.get("items", [])
                for item in items:
                    fn = item.get("full_name", "")
                    if state.is_scanned(fn):
                        continue
                    if item.get("fork") or item.get("archived"):
                        continue
                    repos.append({
                        "full_name": fn,
                        "owner": item.get("owner", {}).get("login", ""),
                        "repo_name": item.get("name", ""),
                        "stars": item.get("stargazers_count", 0),
                        "language": item.get("language", ""),
                        "default_branch": item.get("default_branch", "main"),
                        "html_url": item.get("html_url", ""),
                    })
                if not items:
                    break
                time.sleep(0.5)
            except RuntimeError as e:
                print(f"  [discover] {e}")
                break
    return repos


def scan_issues(repo: dict, state: StateManager) -> list:
    """Get open good-first-issue issues for a repo."""
    fn = repo["full_name"]
    issues = []
    seen = set()

    for label in TARGET_LABELS:
        encoded_label = quote(label, safe="")
        try:
            data = _gh_api(
                f"repos/{fn}/issues?state=open&labels={encoded_label}&sort=updated&direction=desc&per_page=15"
            )
        except (RuntimeError, subprocess.TimeoutExpired):
            continue

        if not isinstance(data, list):
            continue

        for item in data:
            if "pull_request" in item:
                continue
            num = item.get("number")
            if not num or num in seen:
                continue
            seen.add(num)
            title = item.get("title", "")
            body = item.get("body") or ""
            labels = [lbl.get("name", "") for lbl in (item.get("labels") or [])]

            issues.append({
                "repo_full_name": fn,
                "owner": repo["owner"],
                "repo_name": repo["repo_name"],
                "stars": repo["stars"],
                "default_branch": repo["default_branch"],
                "issue_number": num,
                "title": title,
                "body": body[:2000],
                "labels": labels,
                "url": item.get("html_url", ""),
            })

            if len(issues) >= 5:
                break
        if len(issues) >= 5:
            break

    return issues


def score_issue(issue: dict) -> tuple[int, str]:
    """Score an issue for fixability. Returns (score, fix_type)."""
    title_lower = issue["title"].lower()
    body_lower = issue["body"].lower()
    labels_lower = [l.lower() for l in issue["labels"]]
    score = 0
    fix_type = ""

    # Reject hard issues
    for kw in HARD_TITLE_KW:
        if kw in title_lower:
            return (-100, "")

    # Label scoring
    for label in labels_lower:
        if "good first issue" in label:
            score += 30
        if "help wanted" in label:
            score += 15
        if "documentation" in label or "docs" in label:
            score += 25
            if not fix_type:
                fix_type = "documentation"
        if "bug" in label:
            score += 10

    # Keyword scoring
    for kw in FIXABLE_TITLE_KW:
        if kw in title_lower:
            score += 20
            if kw in ("typo", "spelling", "grammar"):
                fix_type = "typo"
            elif kw in ("broken link", "dead link", "404"):
                fix_type = "broken_link"
            elif kw in ("document", "update readme", "update doc"):
                fix_type = "documentation"
            elif kw in ("wrong label", "i18n", "translation"):
                fix_type = "i18n"
            elif kw in ("fix route",):
                fix_type = "simple_bug"
            break

    # Body length: 100-2000 chars is sweet spot
    blen = len(issue["body"])
    if 100 < blen < 2000:
        score += 10
    elif blen > 3000:
        score -= 10

    if not fix_type:
        fix_type = "simple_bug"

    return (score, fix_type)
