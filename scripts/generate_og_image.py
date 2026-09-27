#!/usr/bin/env python3
"""Regenerate the Open Graph link-preview image (issue #440).

Facebook, X and LinkedIn render only raster ``og:image`` previews, so an SVG
logo shows up as a blank card. This script draws a 1200x630 PNG card from the
same artwork as ``static/images/logo.svg`` (the cracker stack and the
"SucharOverflow" wordmark) on the dark favicon background, plus the site
tagline.

It renders through Playwright's Chromium rather than an SVG converter because
the wordmark depends on the self-hosted Fira Code / Inter fonts, which a plain
converter (e.g. ImageMagick) silently swaps for a fallback face. The fonts are
inlined as data URIs from ``static/fonts/``, so no server is needed.

Unlike ``generate_easter_egg_audio.py`` the output is **not** byte-deterministic
across Chromium versions (anti-aliasing and PNG encoding may change), so only
re-run it when the card's design changes, and commit the result.

Usage (Chromium is installed in the local Django image, not on the host)::

    just gen-og-image

Writes ``suchar_overflow/static/images/og-image.png``.
"""

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "suchar_overflow" / "static"
FONTS_DIR = STATIC_DIR / "fonts"
OUTPUT = STATIC_DIR / "images" / "og-image.png"

WIDTH = 1200
HEIGHT = 630

# The default-language (Polish) rendering of base.html's meta description.
TAGLINE = "Agregator dowcipów z krytycznie niskim poziomem wilgotności."

# The cracker stack from logo.svg, verbatim — only the wordmark is laid out
# separately below, in HTML, so it can use the inlined web fonts.
CRACKERS_SVG = """
<svg width="300" height="190" viewBox="0 0 130 82"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <g id="cracker">
      <rect width="70" height="22" rx="4" fill="#E58E26"/>
      <circle cx="15" cy="11" r="2.5" fill="#F3E5AB"/>
      <circle cx="35" cy="11" r="2.5" fill="#F3E5AB"/>
      <circle cx="55" cy="11" r="2.5" fill="#F3E5AB"/>
    </g>
  </defs>
  <g transform="translate(0, 0)">
    <use href="#cracker" x="10" y="55" />
    <use href="#cracker" x="10" y="30" />
    <g transform="translate(35, 0) rotate(15)"><use href="#cracker" /></g>
    <circle cx="95" cy="35" r="3" fill="#E58E26"/>
    <circle cx="110" cy="45" r="2" fill="#E58E26"/>
    <circle cx="102" cy="25" r="2.5" fill="#E58E26"/>
    <circle cx="118" cy="30" r="1.5" fill="#E58E26"/>
  </g>
</svg>
"""


def _font_face(family: str, filename: str, weight: int) -> str:
    data = base64.b64encode((FONTS_DIR / filename).read_bytes()).decode()
    return (
        f"@font-face {{ font-family: '{family}'; font-weight: {weight}; "
        f"src: url(data:font/woff2;base64,{data}) format('woff2'); }}"
    )


def build_html() -> str:
    fonts = "\n".join(
        [
            _font_face("Fira Code", "FiraCode-Regular.woff2", 400),
            _font_face("Fira Code", "FiraCode-Bold.woff2", 700),
            _font_face("Inter", "Inter-Medium.woff2", 500),
        ],
    )
    return f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><style>
{fonts}
html, body {{ margin: 0; width: {WIDTH}px; height: {HEIGHT}px; }}
body {{
  background: #2D2D2D;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 36px;
}}
.wordmark {{ font-family: 'Fira Code', monospace; font-size: 88px; }}
.suchar {{ color: #E58E26; }}
.overflow {{ color: #F3E5AB; font-weight: 700; }}
.tagline {{
  font-family: 'Inter', sans-serif; font-weight: 500;
  font-size: 34px; color: #F3E5AB; opacity: .75;
}}
</style></head><body>
{CRACKERS_SVG}
<div class="wordmark"><span class="suchar">Suchar</span><span
  class="overflow">Overflow</span></div>
<div class="tagline">{TAGLINE}</div>
</body></html>"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.set_content(build_html())
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUTPUT), type="png")
        browser.close()
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
