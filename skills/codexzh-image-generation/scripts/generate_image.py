#!/usr/bin/env python3
"""Generate and download an image through the CodexZH AI Hub image API."""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "https://api.xbai.top/v1"
DEFAULT_MODEL = "nano-banana-2"
KEY_ENV_VARS = ("CODEXZH_API_KEY", "XBAI_API_KEY", "OPENAI_API_KEY")
PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "go.mod",
    "Gemfile",
    "composer.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
)
ASSET_DIR_CANDIDATES = (
    "src/assets/images",
    "src/assets",
    "assets/images",
    "assets",
    "public/images",
    "public",
    "static/images",
    "static",
    "images",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="Prompt to send to the image model.")
    parser.add_argument(
        "--output",
        help="Path for the generated image. If omitted, save under the detected project or Desktop.",
    )
    parser.add_argument(
        "--project-dir",
        help="Project directory to receive image assets. Defaults to detecting from the current directory.",
    )
    parser.add_argument("--filename", help="Filename to use when --output is omitted.")
    parser.add_argument("--api-key", help="API key. Prefer env vars instead of this option.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Image model name.")
    parser.add_argument("--size", default="1024x1024", help="Requested image size.")
    parser.add_argument("--quality", default="standard", help="Requested quality.")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request.")
    parser.add_argument(
        "--response-format",
        choices=("url", "b64_json"),
        default="url",
        help="API response format.",
    )
    parser.add_argument("--response-json", help="Optional path for the raw API response JSON.")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout in seconds.")
    return parser.parse_args()


def find_project_root(start: pathlib.Path) -> pathlib.Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent

    home = pathlib.Path.home().resolve()
    for path in (current, *current.parents):
        if any((path / marker).exists() for marker in PROJECT_MARKERS):
            return path
        if path == home:
            break
    return None


def choose_asset_dir(project_root: pathlib.Path) -> pathlib.Path:
    for candidate in ASSET_DIR_CANDIDATES:
        path = project_root / candidate
        if path.is_dir():
            return path
    return project_root / "assets" / "images"


def default_filename() -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"codexzh-image-{stamp}.jpg"


def resolve_output(args: argparse.Namespace) -> pathlib.Path:
    if args.output:
        return pathlib.Path(args.output).expanduser()

    filename = args.filename or default_filename()
    if pathlib.Path(filename).name != filename:
        raise SystemExit("--filename must be a filename, not a path. Use --output for full paths.")

    if args.project_dir:
        root = pathlib.Path(args.project_dir).expanduser().resolve()
    else:
        root = find_project_root(pathlib.Path.cwd())

    if root:
        return choose_asset_dir(root) / filename

    return pathlib.Path.home() / "Desktop" / filename


def get_api_key(explicit_key: str | None) -> str:
    if explicit_key:
        return explicit_key
    for name in KEY_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    joined = ", ".join(KEY_ENV_VARS)
    raise SystemExit(f"Missing API key. Set one of: {joined}, or pass --api-key.")


def request_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Image API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Image API request failed: {exc}") from exc


def download_url(url: str, output: pathlib.Path, timeout: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "codexzh-image-generation/1.0"})
    tmp_output = output.with_name(output.name + ".part")
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with tmp_output.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        handle.write(chunk)
            tmp_output.replace(output)
            return
        except (urllib.error.URLError, http.client.IncompleteRead) as exc:
            last_error = exc
            if tmp_output.exists():
                tmp_output.unlink()
            if attempt < 3:
                time.sleep(attempt)

    raise SystemExit(f"Image download failed after retries: {last_error}")


def write_b64(data: str, output: pathlib.Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(data))


def main() -> int:
    args = parse_args()
    api_key = get_api_key(args.api_key)
    endpoint = args.base_url.rstrip("/") + "/images/generations"
    output = resolve_output(args)

    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "response_format": args.response_format,
    }

    started = time.time()
    response = request_json(endpoint, payload, api_key, args.timeout)

    if args.response_json:
        response_path = pathlib.Path(args.response_json).expanduser()
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")

    data = response.get("data") or []
    if not data:
        raise SystemExit(f"Image API returned no data: {json.dumps(response, ensure_ascii=False)}")

    first = data[0]
    if first.get("url"):
        download_url(first["url"], output, args.timeout)
    elif first.get("b64_json"):
        write_b64(first["b64_json"], output)
    else:
        raise SystemExit(f"Image API returned no url or b64_json: {json.dumps(first, ensure_ascii=False)}")

    elapsed = time.time() - started
    print(f"Saved image: {output}")
    print(f"Elapsed: {elapsed:.1f}s")
    if args.response_json:
        print(f"Saved response JSON: {pathlib.Path(args.response_json).expanduser()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
