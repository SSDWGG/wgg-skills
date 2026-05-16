#!/usr/bin/env python3
"""Persistent state: scanned repos, candidates, PRs."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Union


class StateManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> Union[dict, list]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_json(self, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def load_candidates(self) -> list:
        return self._read_json(Path(self.data_dir) / "candidates.json") or []

    def save_candidates(self, candidates: list):
        from config import CANDIDATES_FILE
        self._write_json(CANDIDATES_FILE, candidates)

    def load_prs(self) -> Union[dict, list]:
        return self._read_json(Path(self.data_dir) / "prs.json") or {}

    def save_prs(self, prs: dict):
        from config import PRS_FILE
        self._write_json(PRS_FILE, prs)

    def add_pr(self, repo: str, issue_number: int, pr_url: str, pr_number: int, fix_type: str):
        prs = self.load_prs()
        key = f"{repo}#{issue_number}"
        prs[key] = {
            "repo": repo,
            "issue_number": issue_number,
            "pr_url": pr_url,
            "pr_number": pr_number,
            "fix_type": fix_type,
            "state": "OPEN",
            "merged": False,
            "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last_checked": None,
            "reviews": 0,
            "review_state": "PENDING",
            "needs_cla": False,
        }
        self.save_prs(prs)

    def update_pr_status(self, key: str, state: str, merged: bool, reviews: int, review_state: str, needs_cla: bool = False):
        prs = self.load_prs()
        if key in prs:
            prs[key]["state"] = state
            prs[key]["merged"] = merged
            prs[key]["reviews"] = reviews
            prs[key]["review_state"] = review_state
            prs[key]["needs_cla"] = needs_cla
            prs[key]["last_checked"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save_prs(prs)

    def load_scanned(self) -> list:
        data = self._read_json(Path(self.data_dir) / "scanned_repos.json")
        return data if isinstance(data, list) else []

    def save_scanned(self, repos: list[str]):
        from config import SCANNED_FILE
        self._write_json(SCANNED_FILE, repos)

    def is_scanned(self, full_name: str) -> bool:
        return full_name in self.load_scanned()

    def mark_scanned(self, full_name: str):
        scanned = self.load_scanned()
        if full_name not in scanned:
            scanned.append(full_name)
            self.save_scanned(scanned)
