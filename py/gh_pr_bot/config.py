#!/usr/bin/env python3
"""Configuration for gh-pr-bot."""
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))

HOME = Path.home()
OUTPUT_DIR = Path(os.environ.get("BOT_OUTPUT_DIR", str(HOME / ".codex" / "monitoring" / "gh-pr-bot"))).expanduser()
CANDIDATES_FILE = OUTPUT_DIR / "candidates.json"
PRS_FILE = OUTPUT_DIR / "prs.json"
SCANNED_FILE = OUTPUT_DIR / "scanned_repos.json"
RUN_LOG = OUTPUT_DIR / "runs.jsonl"
CLONE_DIR = Path(os.environ.get("BOT_CLONE_DIR", "/tmp/gh-pr-bot-clones")).expanduser()


def _get_gh_token() -> str:
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _get_gh_user() -> str:
    user = os.environ.get("BOT_GH_USER", "").strip()
    if user:
        return user
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


GH_TOKEN = _get_gh_token()
GH_USER = _get_gh_user()

MIN_STARS = int(os.environ.get("BOT_MIN_STARS", "400"))
MAX_STARS = int(os.environ.get("BOT_MAX_STARS", "700"))
MAX_PRS_PER_RUN = int(os.environ.get("BOT_MAX_PRS_PER_RUN", "1"))
MAX_PRS_PER_REPO = int(os.environ.get("BOT_MAX_PRS_PER_REPO", "1"))
RECENCY_MONTHS = int(os.environ.get("BOT_RECENCY_MONTHS", "6"))

RECENCY_DATE = (datetime.utcnow() - timedelta(days=RECENCY_MONTHS * 30)).strftime("%Y-%m-%d")

LANGUAGES = ["typescript", "javascript"]

# Issue labels to look for
TARGET_LABELS = ["good first issue", "good-first-issue", "help wanted", "documentation"]

# Keywords in title/body that suggest a fixable issue
FIXABLE_TITLE_KW = ["typo", "spelling", "grammar", "broken link", "dead link", "404", "document", "wrong label", "i18n", "translation", "fix route", "update readme", "update doc"]
HARD_TITLE_KW = ["feature request", "rfc", "proposal", "refactor", "architecture", "design", "performance", "security"]

# Search query builder
SEARCH_EXCLUDE_TOPICS = ["hacktoberfest", "learning", "example", "tutorial", "demo", "template"]
