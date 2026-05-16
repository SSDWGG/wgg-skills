#!/usr/bin/env python3
"""
gh-pr-bot — Automated GitHub PR scanner, submitter, and tracker.

Commands:
  scan    Discover repos and issues, save candidates
  submit  Submit a PR for the best candidate
  status  Check status of all submitted PRs
  auto    Full auto pipeline: scan → submit → save
  report  Print a markdown report of all PRs and statuses
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))

from config import (
    OUTPUT_DIR, CANDIDATES_FILE, PRS_FILE, RUN_LOG,
    MAX_PRS_PER_RUN, MAX_PRS_PER_REPO, RECENCY_DATE,
    MIN_STARS, MAX_STARS, GH_USER,
)
from state_manager import StateManager
from discover import search_repos, scan_issues, score_issue
from fixer import clone_or_pull
from pr_manager import fork_repo, push_branch, create_pr, check_all_prs, check_pr_status


def log_run(event: str, extra: Optional[dict] = None):
    """Append a JSONL log entry."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
    }
    if extra:
        entry.update(extra)
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_scan(args):
    """Discover repos → scan issues → score → save candidates."""
    state = StateManager(OUTPUT_DIR)
    print("=== Scanning GitHub repos ===")
    print(f"  Stars: {MIN_STARS}..{MAX_STARS}, Languages: typescript/javascript")
    print(f"  Active since: {RECENCY_DATE}")

    pages = getattr(args, "pages", 3)
    limit = getattr(args, "limit", 30)

    repos = search_repos(state, max_pages=pages)
    print(f"\nFound {len(repos)} candidate repos")

    all_candidates = state.load_candidates()
    existing_repos = {c["repo_full_name"] for c in all_candidates}

    for repo in repos:
        if len(all_candidates) >= limit:
            break
        fn = repo["full_name"]
        print(f"\n--- {fn} ({repo['stars']}★) ---")
        issues = scan_issues(repo, state)
        print(f"  {len(issues)} open target issues")

        for issue in issues:
            score, fix_type = score_issue(issue)
            issue["score"] = score
            issue["fix_type"] = fix_type
            print(f"  #{issue['issue_number']}: {issue['title'][:60]}... score={score} type={fix_type}")
            if score >= 30:
                all_candidates.append(issue)
        state.mark_scanned(fn)

    # Sort by score desc
    all_candidates.sort(key=lambda c: c.get("score", 0), reverse=True)
    all_candidates = all_candidates[:limit]
    state.save_candidates(all_candidates)

    print(f"\n=== Saved {len(all_candidates)} candidates to {CANDIDATES_FILE} ===")
    log_run("scan", {"repos_checked": len(repos), "candidates": len(all_candidates)})


def cmd_submit(args):
    """Fork → clone → fix → commit → push → PR."""
    state = StateManager(OUTPUT_DIR)
    prs = state.load_prs()

    # Count existing OPEN PRs
    open_count = sum(1 for p in prs.values() if p.get("state") == "OPEN")
    if open_count >= MAX_PRS_PER_RUN:
        print(f"Already have {open_count} open PRs (limit: {MAX_PRS_PER_RUN}). Use 'status' to check.")
        return

    # Get candidate
    if args.issue_url:
        # Use specified issue
        print(f"Using specified issue: {args.issue_url}")
        issue = _parse_issue_url(args.issue_url)
        if not issue:
            print("Invalid issue URL format. Use: https://github.com/owner/repo/issues/N")
            return
    else:
        # Pick best from candidates
        candidates = state.load_candidates()
        if not candidates:
            print("No candidates. Run 'scan' first.")
            return
        # Filter out already PR'd
        pr_keys = {f"{p['repo']}#{p['issue_number']}" for p in prs.values()}
        available = [c for c in candidates if f"{c['repo_full_name']}#{c['issue_number']}" not in pr_keys]
        if not available:
            print("All candidates already have PRs. Run 'scan' for fresh candidates.")
            return
        issue = available[0]
        print(f"Best candidate: {issue['repo_full_name']}#{issue['issue_number']} "
              f"(score={issue.get('score', '?')}, type={issue.get('fix_type', '?')})")
        print(f"  {issue['title']}")

    owner = issue["owner"]
    repo_name = issue["repo_name"]
    issue_num = issue["issue_number"]
    fix_type = issue.get("fix_type", "simple_bug")
    title = issue["title"]

    # Fork
    try:
        fork_repo(owner, repo_name)
    except RuntimeError as e:
        print(f"Fork failed: {e}")
        return

    # Clone
    clone_dir = clone_or_pull(owner, repo_name)

    # Create branch
    slug = re.sub(r'[^a-z0-9-]', '', title[:30].lower().replace(" ", "-")).strip("-")
    branch = f"fix/issue-{issue_num}-{slug}"[:200]
    subprocess.run(["git", "-C", str(clone_dir), "checkout", "-b", branch], capture_output=True, text=True, check=True)

    print(f"\n  Branch: {branch}")
    print(f"  Clone: {clone_dir}")
    print(f"\n  === MANUAL STEP: Make your fix in {clone_dir} ===")
    print(f"  Fix type: {fix_type}")
    print(f"  Issue: {issue['url']}")
    print(f"\n  After making changes, the script will commit, push, and create the PR.")

    if args.dry_run:
        print("\n  [DRY RUN] Would commit and push, but skipping.")
        return

    input("\n  Press Enter after making your changes...")

    # Commit
    commit_msg = f"fix: {title[:60]}"

    if not push_branch(clone_dir, branch, commit_msg):
        print("Push failed.")
        return

    # Create PR
    body = f"## Summary\nFixes #{issue_num}\n\n## Change\n{issue.get('body', '')[:500]}..."
    pr_url = create_pr(owner, repo_name, branch, issue.get("default_branch", "main"), commit_msg, body)

    if pr_url:
        # Extract PR number from URL
        pr_num = int(pr_url.rstrip("/").split("/")[-1]) if pr_url else 0
        state.add_pr(f"{owner}/{repo_name}", issue_num, pr_url, pr_num, fix_type)
        # Remove from candidates
        candidates = state.load_candidates()
        candidates = [c for c in candidates if not (c["repo_full_name"] == f"{owner}/{repo_name}" and c["issue_number"] == issue_num)]
        state.save_candidates(candidates)
        log_run("submit", {"repo": f"{owner}/{repo_name}", "issue": issue_num, "pr": pr_url})
        print(f"\n=== PR Created: {pr_url} ===")
    else:
        print("\nPR creation failed.")


def cmd_status(args):
    """Check status of all PRs and print report."""
    state = StateManager(OUTPUT_DIR)
    prs = state.load_prs()

    if not prs:
        print("No PRs tracked yet.")
        return

    print(f"=== Checking {len(prs)} PRs ===\n")
    prs = check_all_prs(prs)
    state.save_prs(prs)

    merged = sum(1 for p in prs.values() if p.get("state") == "MERGED")
    open_count = sum(1 for p in prs.values() if p.get("state") == "OPEN")
    closed = sum(1 for p in prs.values() if p.get("state") == "CLOSED")
    needs_cla = sum(1 for p in prs.values() if p.get("needs_cla"))

    print(f"MERGED: {merged} | OPEN: {open_count} | CLOSED: {closed} | Needs CLA: {needs_cla}\n")

    for key, pr in sorted(prs.items()):
        icon = "✅" if pr.get("state") == "MERGED" else "⏳" if pr.get("state") == "OPEN" else "❌"
        print(f"{icon} {pr['repo']}#{pr['issue_number']}")
        print(f"   PR: {pr['pr_url']}")
        print(f"   State: {pr.get('state')} | Reviews: {pr.get('reviews', 0)} | Review: {pr.get('review_state', 'PENDING')}")
        if pr.get("needs_cla"):
            print(f"   ⚠️  Needs CLA signing!")
        print()

    log_run("status", {"total": len(prs), "merged": merged, "open": open_count, "closed": closed})


def cmd_report(args):
    """Generate markdown report."""
    state = StateManager(OUTPUT_DIR)
    prs = state.load_prs()
    prs = check_all_prs(prs)
    state.save_prs(prs)

    output = Path(args.output) if args.output else OUTPUT_DIR / "report.md"

    lines = [
        "# GitHub PR Bot — Status Report",
        f"\n> Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"\n**Total:** {len(prs)} PRs\n",
        "| # | Repo | Stars | Issue | PR | State | Reviews | Notes |",
        "|---|------|-------|-------|----|-------|---------|-------|",
    ]

    for i, (key, pr) in enumerate(sorted(prs.items()), 1):
        state_icon = {"MERGED": "✅", "OPEN": "⏳", "CLOSED": "❌"}.get(pr.get("state", "OPEN"), "⏳")
        notes = []
        if pr.get("needs_cla"):
            notes.append("Need CLA")
        lines.append(
            f"| {i} | {pr['repo']} | ? | #{pr['issue_number']} | "
            f"[PR]({pr['pr_url']}) | {state_icon} {pr.get('state', 'OPEN')} | "
            f"{pr.get('reviews', 0)} | {', '.join(notes)} |"
        )

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report saved to {output}")


def _parse_issue_url(url: str) -> Optional[dict]:
    """Parse a GitHub issue URL into a minimal issue dict."""
    m = re.match(r'https://github\.com/([^/]+)/([^/]+)/issues/(\d+)', url)
    if not m:
        return None
    owner, repo, num = m.groups()
    # Fetch repo info
    import subprocess, json
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}", "--jq", "{default_branch, stargazers_count, language}"],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(r.stdout)
    except Exception:
        info = {"default_branch": "main", "stargazers_count": 0, "language": "unknown"}
    try:
        r2 = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/issues/{num}", "--jq", "{title, body, labels: [.labels[].name]}"],
            capture_output=True, text=True, timeout=10,
        )
        issue_info = json.loads(r2.stdout)
    except Exception:
        issue_info = {"title": "Unknown", "body": "", "labels": []}
    return {
        "owner": owner,
        "repo_name": repo,
        "repo_full_name": f"{owner}/{repo}",
        "issue_number": int(num),
        "title": issue_info.get("title", ""),
        "body": issue_info.get("body", ""),
        "labels": issue_info.get("labels", []),
        "stars": info.get("stargazers_count", 0),
        "default_branch": info.get("default_branch", "main"),
        "url": url,
        "score": 100,
        "fix_type": "simple_bug",
    }


def main():
    parser = argparse.ArgumentParser(description="gh-pr-bot — Automated GitHub PR tool")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Discover repos and save candidates")
    p_scan.add_argument("--pages", type=int, default=3, help="Max search pages")
    p_scan.add_argument("--limit", type=int, default=30, help="Max candidates to save")

    p_submit = sub.add_parser("submit", help="Submit a PR for the best candidate")
    p_submit.add_argument("--issue-url", help="Specific GitHub issue URL")
    p_submit.add_argument("--dry-run", action="store_true", help="Don't actually create PR")

    p_status = sub.add_parser("status", help="Check all tracked PRs")

    p_auto = sub.add_parser("auto", help="Auto scan and submit one PR")
    p_auto.add_argument("--dry-run", action="store_true")

    p_report = sub.add_parser("report", help="Generate markdown report")
    p_report.add_argument("--output", help="Output file path")

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "submit":
        cmd_submit(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "auto":
        cmd_scan(args)
        cmd_submit(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
