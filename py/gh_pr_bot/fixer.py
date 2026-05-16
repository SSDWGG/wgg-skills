#!/usr/bin/env python3
"""Clone repos and apply fixes."""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))

from config import CLONE_DIR


def _run(cmd: list, cwd: Optional[Path] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None, timeout=timeout)


def clone_or_pull(owner: str, repo_name: str) -> Path:
    """Clone repo shallowly, or pull if exists."""
    clone_dir = CLONE_DIR / f"{owner}_{repo_name}"
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    if not (clone_dir / ".git").exists():
        print(f"  [clone] {owner}/{repo_name}")
        _run(["git", "clone", "--depth=1", f"git@github.com:{owner}/{repo_name}.git", str(clone_dir)])
    else:
        print(f"  [pull] {owner}/{repo_name}")
        try:
            _run(["git", "-C", str(clone_dir), "fetch", "--depth=1", "origin"])
            _run(["git", "-C", str(clone_dir), "reset", "--hard", "origin/HEAD"])
        except Exception:
            import shutil
            shutil.rmtree(clone_dir, ignore_errors=True)
            _run(["git", "clone", "--depth=1", f"git@github.com:{owner}/{repo_name}.git", str(clone_dir)])
    return clone_dir


def find_replace_in_file(file_path: Path, old: str, new: str) -> bool:
    """Replace old with new in a file. Returns True if changed."""
    content = file_path.read_text(errors="replace")
    if old in content:
        file_path.write_text(content.replace(old, new))
        return True
    return False


def apply_typofix(clone_dir: Path, issue: dict) -> list:
    """Scan repo for typos mentioned in the issue. Returns list of file changes."""
    # This is a basic implementation; a real one would use the typo_dict module
    title = issue.get("title", "")
    body = issue.get("body", "")
    # Extract quoted words as potential typos
    quoted = re.findall(r'[`"\'](\w{4,})[`"\']', body)
    if not quoted:
        return []
    changes = []
    for root, dirs, files in os.walk(str(clone_dir)):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "dist", "build", "__pycache__"}]
        for fname in files:
            if not fname.endswith((".ts", ".tsx", ".js", ".jsx", ".md", ".json")):
                continue
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(clone_dir))
            text = fpath.read_text(errors="replace")
            for word in quoted:
                if word in text:
                    changes.append({"path": rel, "word": word, "type": "typo"})
    return changes


def apply_simple_fix(clone_dir: Path, issue: dict, fix_type: str) -> list:
    """Apply a simple fix based on issue context. Returns [{path, original, replacement, description}]."""
    files_to_change = []

    if fix_type == "i18n":
        # Find translation files that match the issue description
        body = issue.get("body", "").lower()
        for root, dirs, files in os.walk(str(clone_dir)):
            dirs[:] = [d for d in dirs if "node_modules" not in d]
            for fname in files:
                if fname.endswith(".json") and "locale" in str(root).lower():
                    fpath = Path(root) / fname
                    try:
                        text = fpath.read_text(errors="replace")
                        # Look for quoted strings in issue body that appear in the file
                        quoted = re.findall(r'"([^"]+)"', issue.get("body", ""))
                        for q in quoted:
                            if q in text and len(q) > 2:
                                rel = str(fpath.relative_to(clone_dir))
                                files_to_change.append({
                                    "path": rel,
                                    "original": q,
                                    "replacement": "",  # to be filled by human
                                    "description": f"Fix translation: {q}",
                                })
                    except Exception:
                        pass

    return files_to_change
