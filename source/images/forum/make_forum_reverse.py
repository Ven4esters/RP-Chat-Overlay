#!/usr/bin/env python3
"""Графика для темы на форуме: новая функция «перевод входящего» и две кнопки скачивания.
Ширина ≤ 480 px — форум вставляет [img] в натуральную величину."""

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
  <linearGradient id="green" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#2fa364"/><stop offset="1" stop-color="#6fdd9b"/></linearGradient>
  <linearGradient id="blue" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#2f57b8"/><stop offset="1" stop-color="#5b8bf0"/></linearGradient>
  <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/></linearGradient>
  <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">
    <path d="M26 0H0V26" fill="none" stroke="#ffffff" stroke-opacity="0.035"/></pattern>
</defs>'''


def measure(text, size, bold=False, spacing=0.0):
    return ImageFont.truetype(_F[bold], int(size)).getlength(text) + spacing * max(0, len(text) - 1)


def fit(text, max_w, size, bold=False, spacing=0.0, min_size=8):
    while size > min_size and measure(text, size, bold, spacing) > max_w:
        size -= 1
    return size


def svg(w, h, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}">{DEFS}{body}{{BODY}}</svg>'.replace(
            "{BODY}", ""
        )
    )


def render(name, text):
    (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
    cairosvg.svg2png(bytestring=text.encode(), write_to=str(OUT / f"{name}.png"), scale=1)
    from PIL import Image

    im = Image.open(OUT / f"{name}.png")
    print(
        f"  {name}.png  {im.size[0]}×{im.size[1]}  {(OUT / (name + '.png')).stat().st_size // 1024} КБ"
    )


# ------------------------------------------- баннер новой функции (480 px)
def banner():
    w, h = 480, 108
    title = "Пишете на своём языке"
    sub = "в чат уходит перевод на русский"
    b = [
        f'<rect width="{w}" height="{h}" fill="url(#bg)"/>',
        f'<rect width="{w}" height="{h}" fill="url(#grid)"/>',
        '<circle cx="450" cy="0" r="80" fill="#57c98a" opacity="0.10"/>',
        f'<rect x="0" y="{h - 4}" width="{w}" height="4" fill="url(#bar)"/>',
        '<circle cx="48" cy="46" r="22" fill="#17251c" stroke="#2e6b48"/>',
        '<path d="M38 46h18" stroke="#57c98a" stroke-width="2.6"/>',
        '<path d="M50 40l8 6-8 6z" fill="#57c98a"/>',
        f'<text x="84" y="44" font-size="{fit(title, 370, 24, True)}" font-weight="bold" '
        f'fill="{TXT}">{title}</text>',
    ]
    b.append(f'<text x="85" y="66" font-size="{fit(sub, 370, 14)}" fill="{MUT}">{sub}</text>')
    b.append(
        f'<text x="48" y="94" font-size="12" fill="{DIM}">'
        f"новое в версии 1.1 · включается в настройках</text>"
    )
    return svg(w, h, "".join(b))


# ------------------------------------------------- три шага (480 px)
def flow():
    w, h = 480, 168
    steps = [
        ("1", "Пишете в оверлее на своём языке", "#2f57b8"),
        ("2", "Перевод на русский появляется сразу", "#2e7d4f"),
        ("3", "Enter — и перевод уже в чате сервера", "#2e7d4f"),
    ]
    b = [f'<rect width="{w}" height="{h}" rx="12" fill="{PANEL}" stroke="{BORDER}"/>']
    y = 16
    for num, text, col in steps:
        b.append(f'<circle cx="34" cy="{y + 16}" r="13" fill="{col}"/>')
        b.append(
            f'<text x="34" y="{y + 21}" font-size="14" font-weight="bold" fill="#ffffff" '
            f'text-anchor="middle">{num}</text>'
        )
        b.append(
            f'<text x="58" y="{y + 21}" font-size="{fit(text, 392, 14)}" fill="{TXT}">{text}</text>'
        )
        y += 50
    return svg(w, h, "".join(b))


# --------------------------------------- две кнопки скачивания (480 px)
def btn_exe():
    w, h = 480, 80
    t1, t2 = "Скачать программу", "RPChatOverlay.exe · 37,4 МБ · Windows 10/11"
    s1 = fit(t1, 340, 20, bold=True, spacing=0.4)
    s2 = fit(t2, 336, 11.5)
    b = [
        f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="13" fill="#0b1a12" stroke="#2b7d51"/>',
        f'<rect x="6" y="6" width="{w - 12}" height="{h - 12}" rx="10" fill="url(#green)"/>',
        '<g transform="translate(22,20)"><path d="M14 1v16" stroke="#08220f" stroke-width="4.4" '
        'stroke-linecap="round"/><path d="M6 11l8 8 8-8" fill="none" stroke="#08220f" '
        'stroke-width="4.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M2 25h24" stroke="#08220f" stroke-width="4.4" stroke-linecap="round"/></g>',
        f'<text x="70" y="40" font-size="{s1}" font-weight="bold" fill="#08220f">{t1}</text>',
        f'<text x="72" y="61" font-size="{s2}" fill="#0a3016" opacity="0.9">{t2}</text>',
    ]
    return svg(w, h, "".join(b))


def btn_src():
    w, h = 480, 64
    t1, t2 = "Скачать исходники", "папка source · Python 3.12 + PySide6"
    b = [
        f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="12" fill="#171b24" stroke="{BLUE}" stroke-width="2"/>',
        f'<text x="34" y="40" font-size="17" font-weight="bold" fill="{BLUE}" '
        f'text-anchor="middle">{{ }}</text>',
        f'<text x="62" y="30" font-size="{fit(t1, 390, 17, True, 0.4)}" font-weight="bold" '
        f'fill="{TXT}">{t1}</text>',
        f'<text x="64" y="50" font-size="{fit(t2, 390, 11.5)}" fill="{MUT}">{t2}</text>',
    ]
    return svg(w, h, "".join(b))


if __name__ == "__main__":
    print("рендер (новая функция + кнопки):")
    render("rv_banner", banner())
    render("rv_flow", flow())
    render("sm_btn_exe", btn_exe())
    render("sm_btn_src", btn_src())
