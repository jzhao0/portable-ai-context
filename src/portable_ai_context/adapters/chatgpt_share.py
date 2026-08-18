from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation
from . import chatgpt_html


HOSTS = {"chatgpt.com", "www.chatgpt.com"}


def normalize_share_input(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("https://") or value.startswith("http://"):
        return value
    if value.startswith("chatgpt.com/share/") or value.startswith("www.chatgpt.com/share/"):
        return "https://" + value
    if value.startswith("/share/"):
        return "https://chatgpt.com" + value
    if value.startswith("share/"):
        return "https://chatgpt.com/" + value
    return value


def is_share_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(normalize_share_input(value))
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in HOSTS and parsed.path.startswith("/share/")


def _browser_candidates() -> list[str]:
    candidates: list[str] = []

    # PATH candidates work well on Linux and package-manager installs.
    for name in [
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
        "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave",
    ]:
        path = shutil.which(name)
        if path:
            candidates.append(path)

    # macOS standard application paths.
    home = Path.home()
    mac_paths = [
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        str(home / "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        str(home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
    candidates.extend(p for p in mac_paths if Path(p).is_file())

    # Windows standard locations.
    bases = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    rels = [
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for base in [b for b in bases if b]:
        for rel in rels:
            p = str(Path(base) / rel)
            if Path(p).is_file():
                candidates.append(p)

    seen = set()
    out = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _fetch_http(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/151 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _fetch_browser(url: str, timeout: int = 60) -> str:
    failures: list[str] = []
    for browser in _browser_candidates():
        for headless in ["--headless=new", "--headless"]:
            with tempfile.TemporaryDirectory(prefix="paic-browser-") as profile:
                cmd = [
                    browser, headless, "--disable-gpu", "--disable-extensions",
                    "--no-first-run", "--no-default-browser-check",
                    f"--user-data-dir={profile}", "--virtual-time-budget=8000",
                    "--dump-dom", url,
                ]
                try:
                    proc = subprocess.run(
                        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=timeout,
                    )
                except Exception as exc:
                    failures.append(type(exc).__name__)
                    continue
                if proc.returncode == 0 and chatgpt_html.can_load(proc.stdout):
                    return proc.stdout
                failures.append(f"{Path(browser).name}:{proc.returncode}:{len(proc.stdout)}")
    raise ParseError("browser fallback failed; attempts=" + ",".join(failures[-6:]))


def fetch(url: str) -> str:
    url = normalize_share_input(url)
    if not is_share_url(url):
        raise ParseError("not a ChatGPT shared URL")
    try:
        text = _fetch_http(url)
        if chatgpt_html.can_load(text):
            return text
    except urllib.error.HTTPError as exc:
        if exc.code not in {401, 403, 429}:
            raise
    return _fetch_browser(url)


def load(source: str) -> Conversation:
    url = normalize_share_input(source)
    html = fetch(url)
    conv = chatgpt_html.load(url, html)
    conv.source.kind = "chatgpt_share_url"
    conv.source.locator = url
    return conv
