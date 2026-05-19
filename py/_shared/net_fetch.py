#!/usr/bin/env python3
import os
import shutil
import subprocess
import urllib.request


DEFAULT_UA = "Codex scheduled-fetch/1.0"


def system_proxy_url():
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    scutil = shutil.which("scutil")
    if not scutil:
        return ""
    result = subprocess.run(
        [scutil, "--proxy"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        return ""

    values = {}
    for raw_line in result.stdout.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip()

    if values.get("HTTPSEnable") == "1" and values.get("HTTPSProxy") and values.get("HTTPSPort"):
        return f"http://{values['HTTPSProxy']}:{values['HTTPSPort']}"
    if values.get("HTTPEnable") == "1" and values.get("HTTPProxy") and values.get("HTTPPort"):
        return f"http://{values['HTTPProxy']}:{values['HTTPPort']}"
    return ""


def _curl_args(url, user_agent, proxy_url=""):
    args = [
        "curl",
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "30",
        "-A",
        user_agent,
    ]
    if proxy_url:
        args.extend(["--proxy", proxy_url])
    args.append(url)
    return args


def _run_command(args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode == 0 and result.stdout:
        return result.stdout
    message = result.stderr.decode("utf-8", errors="replace").strip()
    raise RuntimeError(message or f"command failed: {' '.join(args[:3])}")


def _try_gg(args):
    gg = shutil.which("gg")
    if not gg:
        raise RuntimeError("gg not found")
    errors = []
    for prefix in ([gg], [gg, "--"]):
        try:
            return _run_command(prefix + args)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def fetch_url(url, user_agent=DEFAULT_UA, timeout=30, proxy=None):
    errors = []
    curl = shutil.which("curl")
    if curl:
        args = _curl_args(url, user_agent)
        try:
            return _run_command(args)
        except Exception as exc:
            errors.append(f"direct curl: {exc}")

        effective_proxy = proxy or system_proxy_url()
        if effective_proxy:
            try:
                return _run_command(_curl_args(url, user_agent, effective_proxy))
            except Exception as exc:
                errors.append(f"proxy {effective_proxy}: {exc}")

        try:
            return _try_gg(args)
        except Exception as exc:
            errors.append(f"gg proxy: {exc}")

    effective_proxy = proxy or system_proxy_url()
    handlers = []
    if effective_proxy:
        handlers.append(urllib.request.ProxyHandler({"http": effective_proxy, "https": effective_proxy}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:
        errors.append(f"urllib: {exc}")

    raise RuntimeError("fetch failed; " + " | ".join(errors))
