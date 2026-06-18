"""Generate local-first placeholder media for the public reader demo.

Writes lightweight, dark/cinematic SVG placeholders (page frames, covers, a
video poster) into ``backend/app/static/demo/`` so the SUPERVOID Graphic Novel
Webviewer renders real frames with no external/copyrighted assets.

Audio (``theme.mp3``) and video (``intro.mp4``) are intentionally left absent —
the reader is built to degrade gracefully when media is missing or blocked.

Run:  python scripts/generate_demo_assets.py
"""
from __future__ import annotations

from pathlib import Path

# SUPERVOID palette (mirrors the Tailwind tokens).
INK_900, INK_800, INK_700, INK_650 = "#070605", "#0d0c0a", "#141310", "#181612"
PARCHMENT, PARCHMENT_DIM = "#e8e3d3", "#7a7466"
ACCENT, RULE = "#b08456", "#272520"
SERIF = "Georgia, 'EB Garamond', serif"
MONO = "'JetBrains Mono', ui-monospace, monospace"

STATIC = Path(__file__).resolve().parent.parent / "app" / "static" / "demo"


def _write(rel: str, svg: str) -> None:
    path = STATIC / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg.strip() + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(STATIC.parent.parent)}")


def page(n: int, w: int = 1400, h: int = 2000) -> str:
    """A cinematic page frame with faux panels and a page number."""
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{INK_700}"/>
      <stop offset="1" stop-color="{INK_900}"/>
    </linearGradient>
  </defs>
  <rect width="{w}" height="{h}" fill="url(#bg)"/>
  <rect x="40" y="40" width="{w-80}" height="{h-80}" fill="none" stroke="{RULE}" stroke-width="2"/>
  <rect x="90" y="110" width="{w-180}" height="{int(h*0.32)}" fill="{INK_650}" stroke="{RULE}"/>
  <rect x="90" y="{130+int(h*0.32)}" width="{int((w-200)*0.5)}" height="{int(h*0.30)}" fill="{INK_650}" stroke="{RULE}"/>
  <rect x="{110+int((w-200)*0.5)}" y="{130+int(h*0.32)}" width="{int((w-200)*0.5)}" height="{int(h*0.30)}" fill="{INK_650}" stroke="{RULE}"/>
  <rect x="90" y="{150+int(h*0.62)}" width="{w-180}" height="{int(h*0.24)}" fill="{INK_650}" stroke="{RULE}"/>
  <text x="{w//2}" y="{h//2}" fill="{PARCHMENT_DIM}" font-family="{SERIF}" font-size="120" font-style="italic" text-anchor="middle" opacity="0.5">{n:02d}</text>
  <text x="90" y="{h-70}" fill="{PARCHMENT_DIM}" font-family="{MONO}" font-size="26" letter-spacing="6">THE SILENT WORKSHOP</text>
  <text x="{w-90}" y="{h-70}" fill="{ACCENT}" font-family="{MONO}" font-size="26" letter-spacing="6" text-anchor="end">PAGE {n:02d}</text>
</svg>
"""


def cover(title: str, subtitle: str, w: int = 1000, h: int = 1500) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <radialGradient id="cg" cx="0.5" cy="0.35" r="0.9">
      <stop offset="0" stop-color="{INK_650}"/>
      <stop offset="1" stop-color="{INK_900}"/>
    </radialGradient>
  </defs>
  <rect width="{w}" height="{h}" fill="url(#cg)"/>
  <rect x="56" y="56" width="{w-112}" height="{h-112}" fill="none" stroke="{ACCENT}" stroke-width="1.5" opacity="0.7"/>
  <text x="{w//2}" y="150" fill="{PARCHMENT_DIM}" font-family="{MONO}" font-size="22" letter-spacing="10" text-anchor="middle">SUPERVOID · GRAPHIC NOVEL</text>
  <text x="{w//2}" y="{h//2-40}" fill="{PARCHMENT}" font-family="{SERIF}" font-size="92" text-anchor="middle">{title}</text>
  <text x="{w//2}" y="{h//2+40}" fill="{PARCHMENT_DIM}" font-family="{SERIF}" font-size="40" font-style="italic" text-anchor="middle">{subtitle}</text>
  <line x1="{w//2-120}" y1="{h-180}" x2="{w//2+120}" y2="{h-180}" stroke="{ACCENT}" stroke-width="1.5"/>
  <text x="{w//2}" y="{h-130}" fill="{PARCHMENT_DIM}" font-family="{MONO}" font-size="20" letter-spacing="6" text-anchor="middle">SAOIRSE CARRICK</text>
</svg>
"""


def poster(w: int = 1600, h: int = 900) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="{INK_900}"/>
  <rect x="40" y="40" width="{w-80}" height="{h-80}" fill="none" stroke="{RULE}"/>
  <circle cx="{w//2}" cy="{h//2}" r="70" fill="none" stroke="{ACCENT}" stroke-width="2"/>
  <path d="M{w//2-22},{h//2-34} L{w//2+40},{h//2} L{w//2-22},{h//2+34} Z" fill="{ACCENT}"/>
  <text x="{w//2}" y="{h-90}" fill="{PARCHMENT_DIM}" font-family="{MONO}" font-size="24" letter-spacing="8" text-anchor="middle">INTRO · THE SILENT WORKSHOP</text>
</svg>
"""


def main() -> None:
    print(f"Generating demo assets into {STATIC} ...")
    for i in range(1, 7):
        _write(f"pages/page-{i:03d}.svg", page(i))
    _write("covers/silent-workshop.svg", cover("The Silent Workshop", "A correspondence in ink"))
    _write("covers/silent-workshop-vol1.svg", cover("Volume One", "Letters Unsent"))
    _write("video/intro-poster.svg", poster())
    print("Done.")


if __name__ == "__main__":
    main()
