"""Generate the 1200x630 OG poster used as the og:image for X / Pages cards.

Run from the repo root:

    pip install pillow
    python scripts/generate_posters.py

Writes docs/posters/og-default.png. Re-run any time the brand text changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "docs" / "posters" / "og-default.png"

WIDTH, HEIGHT = 1200, 630
BG = (11, 15, 23)            # #0b0f17
ACCENT = (0, 229, 255)       # #00E5FF
ACCENT_2 = (124, 58, 237)    # #7C3AED
ACCENT_3 = (255, 79, 216)    # #FF4FD8
WHITE = (234, 248, 255)      # #EAF8FF
MUTED = (140, 160, 180)

TITLE = "grok-install"
TAGLINE = "The npm install for Grok agents"
SUBLINE = "YAML in. Live agent out. Safety gate built in."
URL = "agentmindcloud.github.io/grok-install-cli"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _gradient_stripe(img: Image.Image, y0: int, y1: int) -> None:
    """Horizontal cyan -> purple -> magenta stripe across the top."""
    pixels = img.load()
    span = WIDTH
    for x in range(span):
        t = x / max(1, span - 1)
        if t < 0.5:
            u = t / 0.5
            r = int(ACCENT[0] * (1 - u) + ACCENT_2[0] * u)
            g = int(ACCENT[1] * (1 - u) + ACCENT_2[1] * u)
            b = int(ACCENT[2] * (1 - u) + ACCENT_2[2] * u)
        else:
            u = (t - 0.5) / 0.5
            r = int(ACCENT_2[0] * (1 - u) + ACCENT_3[0] * u)
            g = int(ACCENT_2[1] * (1 - u) + ACCENT_3[1] * u)
            b = int(ACCENT_2[2] * (1 - u) + ACCENT_3[2] * u)
        for y in range(y0, y1):
            pixels[x, y] = (r, g, b)


def render() -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    _gradient_stripe(img, 0, 12)
    _gradient_stripe(img, HEIGHT - 12, HEIGHT)

    title_font = _font(FONT_CANDIDATES, 110)
    tagline_font = _font(FONT_CANDIDATES, 46)
    subline_font = _font(FONT_CANDIDATES, 32)
    url_font = _font(MONO_CANDIDATES, 26)

    draw.text((80, 150), TITLE, font=title_font, fill=WHITE)
    draw.text((80, 290), TAGLINE, font=tagline_font, fill=ACCENT)
    draw.text((80, 360), SUBLINE, font=subline_font, fill=MUTED)
    draw.text((80, HEIGHT - 80), URL, font=url_font, fill=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    return OUT


if __name__ == "__main__":
    out = render()
    print(f"wrote {out} ({out.stat().st_size} bytes)")
