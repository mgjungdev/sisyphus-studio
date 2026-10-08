"""Rasterize site/img/icon.svg into the PNG app icons (Playwright chromium; no image library needed).

Outputs  site/img/icon-192.png, icon-512.png (manifest, "any maskable"), apple-touch-icon.png (180, iOS home screen)
The SVG is full-bleed with the mark inside the maskable safe zone (centre circle, 40% radius), so one file serves both.

Usage: python tools/icons.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "site" / "img"
SIZES = {"icon-192.png": 192, "icon-512.png": 512, "apple-touch-icon.png": 180}


def main() -> int:
    from playwright.sync_api import sync_playwright
    svg = (IMG / "icon.svg").read_text(encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for name, px in SIZES.items():
                page = browser.new_page(viewport={"width": px, "height": px}, device_scale_factor=1)
                page.set_content(f'<style>html,body{{margin:0}}svg{{display:block;width:{px}px;height:{px}px}}</style>{svg}')
                page.screenshot(path=str(IMG / name), clip={"x": 0, "y": 0, "width": px, "height": px})
                page.close()
                print(IMG / name)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
