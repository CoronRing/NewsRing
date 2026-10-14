"""The daily top stories card: an HTML layout, screenshotted to PNG.

The card is 1200×630 CSS pixels, the size social networks and GitHub use for
link previews, rendered at 2× so text stays sharp on high-density screens. It
has two parts: the day's top stories on the left, and on the right a panel
inviting the reader to get their own feed.

Rendering uses any Chromium-based browser in headless mode, which every
GitHub-hosted runner already has (`google-chrome`) and every Windows machine
has as Edge. No browser automation library is needed. Set `NEWSRING_BROWSER`
to a binary path to choose one explicitly.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from newsring.models import DigestHeadline

logger = logging.getLogger(__name__)

WIDTH = 1200
HEIGHT = 630
SCALE = 2

_BROWSER_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "msedge",
)
_BROWSER_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)

_FONTS = (
    "https://fonts.googleapis.com/css2?family=Archivo:wght@600;800"
    "&family=Inter:wght@400;500&family=JetBrains+Mono:wght@500;700&display=block"
)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1200px; height: 630px; overflow: hidden; }
body {
  background: #0a0a0b; color: #f5f5f5;
  font-family: Inter, 'Segoe UI', system-ui, sans-serif;
  display: grid; grid-template-columns: 1fr 340px;
}
.mono { font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace; }
.news { position: relative; padding: 44px 48px 40px 56px; display: flex; flex-direction: column; }
.news::before {
  content: ""; position: absolute; inset: 0;
  background-image: radial-gradient(rgba(255,255,255,.055) 1px, transparent 1px);
  background-size: 22px 22px; pointer-events: none;
}
.top { display: flex; align-items: center; gap: 14px; font-size: 13px; letter-spacing: .14em; text-transform: uppercase; color: #a0a0a6; }
.badge { background: #fffa00; color: #0a0a0b; font-weight: 700; padding: 5px 10px; letter-spacing: .12em; }
.stories { margin-top: 30px; display: flex; flex-direction: column; gap: 22px; flex: 1; }
.story { display: grid; grid-template-columns: 64px 1fr; position: relative; }
.num { font-size: 40px; font-weight: 700; color: #fffa00; line-height: 1; padding-top: 2px; }
.kicker { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: #fffa00; opacity: .85; }
.headline {
  font-family: Archivo, Inter, sans-serif; font-weight: 800; font-size: 29px; line-height: 1.12;
  letter-spacing: -.01em; margin-top: 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.blurb {
  font-size: 16px; line-height: 1.4; color: #b4b4ba; margin-top: 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.source { font-size: 11.5px; color: #6f6f76; margin-top: 6px; letter-spacing: .04em; }
.panel {
  background: #fffa00; color: #0a0a0b; padding: 44px 34px 38px;
  display: flex; flex-direction: column; position: relative; overflow: hidden;
}
.ring {
  position: absolute; right: -120px; top: -120px; width: 320px; height: 320px;
  border: 26px solid rgba(10,10,11,.09); border-radius: 50%;
}
.ring.small { right: auto; left: -60px; top: auto; bottom: -70px; width: 180px; height: 180px; border-width: 16px; }
.brand { font-family: Archivo, Inter, sans-serif; font-weight: 800; font-size: 42px; letter-spacing: -.02em; position: relative; }
.pitch { font-family: Archivo, Inter, sans-serif; font-weight: 600; font-size: 25px; line-height: 1.2; margin-top: 26px; position: relative; }
.points { margin-top: 22px; display: flex; flex-direction: column; gap: 9px; font-size: 15px; position: relative; }
.points div::before { content: "→ "; font-weight: 700; }
.cta { margin-top: auto; position: relative; }
.cta .label { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; opacity: .7; }
.cta .url { font-size: 13.5px; font-weight: 700; margin-top: 8px; background: #0a0a0b; color: #fffa00; padding: 10px 12px; display: block; white-space: nowrap; }
.empty { margin-top: 60px; font-size: 22px; color: #a0a0a6; }
"""


def _host(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.") or url


def _display_url(url: str) -> str:
    parts = urlsplit(url)
    return (parts.netloc.removeprefix("www.") + parts.path).rstrip("/")


def card_html(headlines: list[DigestHeadline], *, day: date, project_url: str) -> str:
    """Lay out the card as a standalone HTML page.

    Args:
        headlines: The day's top stories. Three fit best; up to five fit.
        day: The date printed on the card.
        project_url: Where readers can get their own feed.

    Returns:
        A complete HTML document sized exactly 1200×630.
    """
    rows = []
    for n, story in enumerate(headlines, start=1):
        rows.append(
            f'<div class="story"><div class="num mono">{n:02d}</div><div>'
            f'<div class="kicker mono">{escape(story.kicker)}</div>'
            f'<div class="headline">{escape(story.headline)}</div>'
            f'<div class="blurb">{escape(story.blurb)}</div>'
            f'<div class="source mono">{escape(_host(story.item.url))}</div>'
            "</div></div>"
        )
    stories = "".join(rows) or '<div class="empty">A quiet few days. Nothing made the cut.</div>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{_FONTS}">
<style>{_CSS}</style></head>
<body>
<section class="news">
  <div class="top mono"><span class="badge">AI news today</span><span>{escape(day.strftime("%a %d %b %Y"))}</span></div>
  <div class="stories">{stories}</div>
</section>
<aside class="panel">
  <div class="ring"></div><div class="ring small"></div>
  <div class="brand">NewsRing</div>
  <div class="pitch">Your own AI news feed, picked for you and written your way.</div>
  <div class="points">
    <div>Your interests, your tone</div>
    <div>No ads, no sponsors</div>
    <div>Open source, runs free</div>
  </div>
  <div class="cta"><div class="label mono">Get yours</div><div class="url mono">{escape(_display_url(project_url))}</div></div>
</aside>
</body></html>
"""


def find_browser() -> str | None:
    """Locate a Chromium-based browser binary.

    Returns:
        The path from `NEWSRING_BROWSER`, else the first browser found on
        `PATH` or in its usual install location, else None.
    """
    explicit = os.environ.get("NEWSRING_BROWSER")
    if explicit:
        return explicit
    for name in _BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return next((p for p in _BROWSER_PATHS if Path(p).exists()), None)


def render_png(html: str, out: Path, *, timeout: float = 60.0) -> bool:
    """Screenshot an HTML card to a PNG with a headless browser.

    Args:
        html: The card page from `card_html`.
        out: Where to write the PNG. Its directory is created if needed.
        timeout: Seconds to allow the browser.

    Returns:
        True if the PNG was written. False, with a warning logged, if no
        browser is available or it failed, so a missing image never fails a run.
    """
    browser = find_browser()
    if browser is None:
        logger.warning("No Chromium-based browser found; card image skipped. Set NEWSRING_BROWSER.")
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "card.html"
        page.write_text(html, encoding="utf-8")
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--mute-audio",
            f"--user-data-dir={Path(tmp) / 'profile'}",
            f"--window-size={WIDTH},{HEIGHT}",
            f"--force-device-scale-factor={SCALE}",
            # Lets web fonts load before the shot is taken.
            "--virtual-time-budget=10000",
            f"--screenshot={out.resolve()}",
            page.resolve().as_uri(),
        ]
        try:
            subprocess.run(command, check=True, timeout=timeout, capture_output=True)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Card screenshot failed with %s: %s", browser, exc)
            return False
    if not out.exists() or out.stat().st_size == 0:
        logger.warning("Card screenshot produced no file")
        return False
    return True
