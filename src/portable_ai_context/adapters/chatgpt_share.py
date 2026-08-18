from __future__ import annotations

import ntpath
import os
import platform
import posixpath
import re
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
SHARE_ID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")

PATH_BROWSER_NAMES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "microsoft-edge-stable",
    "brave-browser",
    "brave",
]

WINDOWS_APP_PATH_EXES = ["chrome.exe", "msedge.exe", "brave.exe", "chromium.exe"]


def normalize_share_input(value: str) -> str:
    """Normalize common ChatGPT shared-link forms without touching local paths."""
    value = (value or "").strip()
    if value.startswith("https://") or value.startswith("http://"):
        return value
    if value.startswith("chatgpt.com/share/") or value.startswith("www.chatgpt.com/share/"):
        return "https://" + value
    if value.startswith("/share/"):
        return "https://chatgpt.com" + value
    if value.startswith("share/"):
        return "https://chatgpt.com/" + value
    if SHARE_ID_RE.fullmatch(value):
        return "https://chatgpt.com/share/" + value
    return value


def is_share_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(normalize_share_input(value))
    except Exception:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower() in HOSTS
        and parsed.path.startswith("/share/")
    )


def _platform_browser_paths(
    system_name: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> list[str]:
    """Return platform-specific browser executable paths without probing them.

    Candidate generation uses the *target platform's* path semantics rather than
    the host runner's semantics. That lets Windows CI validate macOS discovery
    (and vice versa) without silently rewriting separators.
    """
    system_name = (system_name or platform.system()).lower()
    environ = environ if environ is not None else dict(os.environ)
    home = home or Path.home()

    if system_name == "darwin":
        home_posix = str(home).replace("\\", "/")
        if home_posix and not home_posix.startswith("/"):
            home_posix = "/" + home_posix.lstrip("/")
        return [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            posixpath.join(home_posix, "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            posixpath.join(home_posix, "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            posixpath.join(home_posix, "Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            posixpath.join(home_posix, "Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]

    if system_name == "windows":
        bases = [
            environ.get("PROGRAMFILES"),
            environ.get("PROGRAMFILES(X86)"),
            environ.get("LOCALAPPDATA"),
        ]
        rels = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
            r"Chromium\Application\chrome.exe",
        ]
        return [
            ntpath.join(base, rel)
            for base in bases
            if base
            for rel in rels
        ]

    if system_name == "linux":
        return [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
            "/usr/bin/brave-browser",
            "/usr/local/bin/google-chrome",
            "/usr/local/bin/chromium",
            "/snap/bin/chromium",
            "/snap/bin/brave",
        ]

    return []


def _windows_registry_candidates() -> list[str]:
    """Read Windows App Paths entries when available.

    This is best-effort and returns only executable paths. Registry errors are
    intentionally swallowed because browser discovery must remain optional.
    """
    if platform.system().lower() != "windows":
        return []

    try:
        import winreg  # type: ignore
    except ImportError:
        return []

    roots = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    views = [0]
    for flag_name in ["KEY_WOW64_64KEY", "KEY_WOW64_32KEY"]:
        flag = getattr(winreg, flag_name, 0)
        if flag and flag not in views:
            views.append(flag)

    found: list[str] = []
    for root in roots:
        for exe in WINDOWS_APP_PATH_EXES:
            key_name = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            for view in views:
                try:
                    with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ | view) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                except OSError:
                    continue
                if isinstance(value, str) and value.strip():
                    found.append(value.strip().strip('"'))
    return found


def _browser_candidates() -> list[str]:
    candidates: list[str] = []

    configured = os.environ.get("PAIC_BROWSER", "").strip()
    if configured:
        configured_path = shutil.which(configured) or configured
        if Path(configured_path).is_file():
            candidates.append(configured_path)

    for name in PATH_BROWSER_NAMES:
        path = shutil.which(name)
        if path:
            candidates.append(path)

    candidates.extend(
        path
        for path in _platform_browser_paths()
        if Path(path).is_file()
    )
    candidates.extend(
        path
        for path in _windows_registry_candidates()
        if Path(path).is_file()
    )

    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        normalized = os.path.normcase(os.path.abspath(item))
        if normalized not in seen:
            seen.add(normalized)
            out.append(item)
    return out


def _browser_command(browser: str, profile: str, headless: str, url: str) -> list[str]:
    """Build the isolated Chromium-family capture command.

    The command always points Chromium at a fresh temporary profile and never at
    the user's normal browser profile/cookies.
    """
    return [
        browser,
        headless,
        "--disable-gpu",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=8000",
        "--dump-dom",
        url,
    ]


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
    browsers = _browser_candidates()
    if not browsers:
        raise ParseError(
            "browser fallback failed; no supported Chromium-family browser found; "
            "set PAIC_BROWSER to an executable path if installed in a nonstandard location"
        )

    failures: list[str] = []
    for browser in browsers:
        for headless in ["--headless=new", "--headless"]:
            with tempfile.TemporaryDirectory(prefix="paic-browser-") as profile:
                cmd = _browser_command(browser, profile, headless, url)
                try:
                    proc = subprocess.run(
                        cmd,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired:
                    failures.append(f"{Path(browser).name}:timeout")
                    continue
                except OSError as exc:
                    failures.append(f"{Path(browser).name}:{type(exc).__name__}")
                    continue
                if proc.returncode == 0 and chatgpt_html.can_load(proc.stdout):
                    return proc.stdout
                failures.append(f"{Path(browser).name}:{proc.returncode}:{len(proc.stdout)}")
    raise ParseError("browser fallback failed; attempts=" + ",".join(failures[-6:]))


def fetch(url: str) -> str:
    url = normalize_share_input(url)
    if not is_share_url(url):
        raise ParseError("not a ChatGPT shared URL")

    http_failure: str | None = None
    try:
        text = _fetch_http(url)
        if chatgpt_html.can_load(text):
            return text
        http_failure = "direct HTTP returned a page without conversation data"
    except urllib.error.HTTPError as exc:
        if exc.code not in {401, 403, 429}:
            raise ParseError(f"direct HTTP failed with unexpected status {exc.code}") from exc
        http_failure = f"direct HTTP blocked with status {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        http_failure = f"direct HTTP transport failed: {type(exc).__name__}"

    try:
        return _fetch_browser(url)
    except ParseError as exc:
        detail = f"; {http_failure}" if http_failure else ""
        raise ParseError(f"ChatGPT shared-URL capture failed{detail}; browser fallback: {exc}") from exc


def load(source: str) -> Conversation:
    url = normalize_share_input(source)
    html = fetch(url)
    conv = chatgpt_html.load(url, html)
    conv.source.kind = "chatgpt_share_url"
    conv.source.locator = url
    return conv
