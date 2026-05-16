#!/usr/bin/env python3
"""Fork repos, create branches, push, and manage PRs."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))

from config import GH_TOKEN, GH_USER, CLONE_DIR


def _gh_api(endpoint: str, method: str = "GET") -> Union[dict, list]:
    args = ["gh", "api", endpoint]
    if method != "GET":
        args.extend(["--method", method])
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {endpoint}: {r.stderr.strip()}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {}


def fork_repo(owner: str, repo_name: str) -> str:
    """Fork a repo and return the fork URL."""
    print(f"  [fork] {owner}/{repo_name}")
    r = subprocess.run(
        ["gh", "repo", "fork", f"{owner}/{repo_name}", "--clone=false"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Fork failed: {r.stderr.strip()}")
    return f"https://github.com/{GH_USER}/{repo_name}"


def push_branch(clone_dir: Path, branch_name: str, commit_msg: str) -> bool:
    """Commit and push a branch to origin. Returns True on success."""
    try:
        subprocess.run(["git", "-C", str(clone_dir), "add", "-A"], capture_output=True, text=True, timeout=10, check=True)
        subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", commit_msg], capture_output=True, text=True, timeout=10, check=True)
        token = GH_TOKEN
        subprocess.run(
            ["git", "-C", str(clone_dir), "remote", "set-url", "origin",
             f"https://{GH_USER}:{token}@github.com/{GH_USER}/{clone_dir.name.split('_', 1)[1]}.git"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "-c", "http.version=HTTP/1.1", "push", "origin", branch_name],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [push error] {e.stderr.strip() if e.stderr else str(e)}")
        return False


def create_pr(owner: str, repo_name: str, branch: str, base: str, title: str, body: str) -> Optional[str]:
    """Create a PR. Returns PR URL on success."""
    try:
        r = subprocess.run(
            ["gh", "pr", "create",
             "--repo", f"{owner}/{repo_name}",
             "--head", f"{GH_USER}:{branch}",
             "--base", base,
             "--title", title,
             "--body", body],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            url = r.stdout.strip()
            print(f"  [pr] {url}")
            return url
        else:
            print(f"  [pr error] {r.stderr.strip()}")
            return None
    except Exception as e:
        print(f"  [pr error] {e}")
        return None


def check_pr_status(pr_url: str) -> Optional[dict]:
    """Check a PR's status using gh pr view."""
    try:
        r = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "state,mergedAt,mergeStateStatus,reviewDecision,reviews,comments"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None


def check_all_prs(prs: dict) -> dict:
    """Check status of all tracked PRs. Returns updated dict."""
    for key, pr in prs.items():
        if pr.get("state") == "MERGED":
            continue
        url = pr.get("pr_url", "")
        if not url:
            continue
        status = check_pr_status(url)
        if not status:
            continue
        merged = status.get("mergedAt") is not None
        state = "MERGED" if merged else status.get("state", "OPEN")
        reviews = len(status.get("reviews", []) or [])
        review_decision = status.get("reviewDecision", "PENDING") or "PENDING"

        # Check for CLA
        needs_cla = False
        try:
            comments = status.get("comments", [])
            for c in (comments or []):
                if "CLA" in (c.get("body") or "") or "cla" in (c.get("body") or "").lower():
                    needs_cla = True
        except Exception:
            pass

        pr["state"] = state
        pr["merged"] = merged
        pr["reviews"] = reviews
        pr["review_state"] = review_decision
        pr["needs_cla"] = needs_cla

    return prs
