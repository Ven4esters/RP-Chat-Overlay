#!/usr/bin/env python3
"""Графика к теме форума: блок «сленг и сокращения» (ширина 480 px)."""

import pathlib

import cairosvg
from PIL import ImageFont

OUT = pathlib.Path(__file__).parent
PANEL, BORDER = "#1a1d26", "#2b3040"
TXT, DIM, MUT = "#f2f4f8", "#b9c0d4", "#78829a"
BLUE, GREEN = "#3d6fd8", "#57c98a"
FONT = "DejaVu Sans, Segoe UI, Roboto, Arial, sans-serif"
_F = {
    False: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    True: "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}

DEFS = f'''<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0e1017"/><stop offset="0.55" stop-color="#151824"/>
    <stop offset="1" stop-color="#0f1319"/></linearGradient>
  <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/></linearGradient>
  <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">
    <path d="M26 0H0V26" fill="none" stroke="#ffffff" stroke-opacity="0.035"/></pattern>
</defs>'''


def measure(text, size, bold=False):
    return ImageFont.truetype(_F[bold], int(size)).getlength(text)


def fit(text, max_w, size, bold=False, min_size=8):
    while size > min_size and measure(text, size, bold) > max_w:
        size -= 1
    return size


def svg(w, h, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}">{DEFS}{body}</svg>'
    )


def render(name, text):
    (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
    cairosvg.svg2png(bytestring=text.encode(), write_to=str(OUT / f"{name}.png"), scale=1)
    from PIL import Image

    im = Image.open(OUT / f"{name}.png")
    print(
        f"  {name}.png  {im.size[0]}×{im.size[1]}  {(OUT / (name + '.png')).stat().st_size // 1024} КБ"
    )


ROWS = [
    ("lol", "ахах"),
    ("brb", "скоро вернусь"),
    ("afk", "не за клавиатурой"),
    ("idk", "не знаю"),
    ("ty · np", "спасибо · не за что"),
    ("gg", "хорошая игра"),
]


def slang_card():
    """Карточка «сокращение → лаконичный русский вариант»."""
    w, h = 480, 214
    b = [
        f'<rect width="{w}" height="{h}" fill="url(#bg)"/>',
        f'<rect width="{w}" height="{h}" fill="url(#grid)"/>',
        '<circle cx="452" cy="6" r="76" fill="#57c98a" opacity="0.09"/>',
        f'<rect x="0" y="{h - 4}" width="{w}" height="4" fill="url(#bar)"/>',
        f'<text x="28" y="34" font-size="15" font-weight="bold" fill="{TXT}">'
        f"Сленг и сокращения раскрываются до перевода</text>",
        f'<text x="28" y="54" font-size="11.5" fill="{MUT}">'
        f"поэтому падеж, род и время в русской строке сразу верные</text>",
    ]
    y = 80
    for en, ru in ROWS:
        size_en = fit(en, 96, 15, True)
        size_ru = fit(ru, 236, 14)
        b.append(
            f'<text x="28" y="{y}" font-size="{size_en}" font-weight="bold" '
            f'fill="{GREEN}" font-family="DejaVu Sans Mono, Consolas, monospace">{en}</text>'
        )
        b.append(f'<text x="140" y="{y - 1}" font-size="12" fill="{MUT}">→</text>')
        b.append(f'<text x="168" y="{y}" font-size="{size_ru}" fill="{DIM}">{ru}</text>')
        y += 21
    b.append(
        f'<text x="28" y="{h - 14}" font-size="10.5" fill="{MUT}">'
        f"looool · xD · wp · ez · omw · tbh · wdym · asap · rp · ooc и ещё 60</text>"
    )
    return svg(w, h, "".join(b))


if __name__ == "__main__":
    render("sl_slang", slang_card())
