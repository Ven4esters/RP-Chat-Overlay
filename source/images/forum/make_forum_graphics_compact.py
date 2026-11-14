#!/usr/bin/env python3
"""Компактная графика для форума: ширина 440–680 px.

Почему так: форумы вставляют [img] в натуральную величину и не масштабируют —
картинка шире контентной колонки «убегает» за экран. 680 px безопасно почти
для любого форума (контентная колонка обычно 700–900 px).

SVG -> PNG 1:1 (scale=1), палитра как у приложения.
"""
import pathlib
import cairosvg
from PIL import ImageFont

OUT = pathlib.Path(__file__).parent
PANEL, BORDER = "#1a1d26", "#2b3040"
TXT, DIM, MUT = "#f2f4f8", "#b9c0d4", "#78829a"
BLUE, GREEN = "#3d6fd8", "#57c98a"
FONT = "DejaVu Sans, Segoe UI, Roboto, Arial, sans-serif"
_F = {False: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
      True: "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"}

DEFS = f'''<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0e1017"/><stop offset="0.55" stop-color="#151824"/>
    <stop offset="1" stop-color="#0f1319"/></linearGradient>
  <linearGradient id="logo" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/></linearGradient>
  <linearGradient id="green" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#2fa364"/><stop offset="1" stop-color="#6fdd9b"/></linearGradient>
  <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/></linearGradient>
  <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
    <path d="M30 0H0V30" fill="none" stroke="#ffffff" stroke-opacity="0.035"/></pattern>
</defs>'''


def measure(text, size, bold=False, spacing=0.0):
    return ImageFont.truetype(_F[bold], int(size)).getlength(text) + spacing * max(0, len(text) - 1)


def fit(text, max_w, size, bold=False, spacing=0.0, min_size=9):
    while size > min_size and measure(text, size, bold, spacing) > max_w:
        size -= 1
    return size


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{FONT}">{DEFS}{body}</svg>')


def render(name, text):
    (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
    cairosvg.svg2png(bytestring=text.encode(), write_to=str(OUT / f"{name}.png"), scale=1)
    from PIL import Image
    im = Image.open(OUT / f"{name}.png")
    print(f"  {name}.png  {im.size[0]}×{im.size[1]}  {(OUT/(name+'.png')).stat().st_size//1024} КБ")


# ------------------------------------------------------- шапка (680 px)
def header():
    w, h = 680, 196
    b = [f'<rect width="{w}" height="{h}" fill="url(#bg)"/>',
         f'<rect width="{w}" height="{h}" fill="url(#grid)"/>',
         '<circle cx="640" cy="6" r="130" fill="#3d6fd8" opacity="0.10"/>',
         '<circle cx="30" cy="190" r="96" fill="#57c98a" opacity="0.08"/>',
         f'<rect x="0" y="{h-4}" width="{w}" height="4" fill="url(#bar)"/>',
         '<rect x="32" y="30" width="64" height="64" rx="16" fill="url(#logo)"/>',
         '<text x="64" y="72" font-size="27" font-weight="bold" fill="#0d1018" '
         'text-anchor="middle">RP</text>']

    title = "RP Chat Overlay"
    b.append(f'<text x="110" y="62" font-size="{fit(title, 520, 30, True)}" font-weight="bold" '
             f'fill="{TXT}">{title}</text>')
    sub = "переводчик чата для GTA V / FiveM"
    b.append(f'<text x="111" y="87" font-size="{fit(sub, 520, 15)}" fill="{MUT}">{sub}</text>')

    x = 32
    for c in ["13 языков", "свои словари", "слова-паразиты", "Windows 10/11"]:
        cw = int(measure(c, 13)) + 22
        b.append(f'<rect x="{x}" y="106" width="{cw}" height="27" rx="13" fill="#1c2029" stroke="{BORDER}"/>')
        b.append(f'<text x="{x + cw/2}" y="124" font-size="13" fill="{DIM}" text-anchor="middle">{c}</text>')
        x += cw + 7

    src, dst = "Слушай, брат, подожди", "Senti, fratello, aspetta"
    ax = int(32 + measure(src, 14) + 16)          # стрелка строго после текста
    b.append(f'<text x="32" y="172" font-size="14" fill="{DIM}">{src}</text>')
    b.append(f'<path d="M{ax} 166h24" stroke="{GREEN}" stroke-width="2.2"/>')
    b.append(f'<path d="M{ax+20} 161l8 5-8 5z" fill="{GREEN}"/>')
    b.append(f'<text x="{ax+40}" y="172" font-size="{fit(dst, 660 - ax - 40, 14)}" '
             f'fill="#9fe3b5">{dst}</text>')
    return svg(w, h, "".join(b))


# --------------------------------------------- заголовок раздела (680 px)
def section(name, title, caption="", color=BLUE, icon="›"):
    w, h = 680, 56
    ts = fit(title, 380 if caption else 540, 19, bold=True, spacing=0.9)
    b = [f'<rect width="{w}" height="{h}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
         f'<rect x="0" y="0" width="6" height="{h}" rx="3" fill="{color}"/>',
         f'<circle cx="38" cy="{h/2}" r="14" fill="{color}" opacity="0.18"/>',
         f'<text x="38" y="{h/2+6}" font-size="16" font-weight="bold" fill="{color}" '
         f'text-anchor="middle">{icon}</text>',
         f'<text x="64" y="{h/2+6}" font-size="{ts}" font-weight="bold" fill="{TXT}" '
         f'letter-spacing="0.9">{title}</text>']
    if caption:
        b.append(f'<text x="{w-16}" y="{h/2+4}" font-size="{fit(caption, 180, 12)}" '
                 f'fill="{MUT}" text-anchor="end">{caption}</text>')
    return svg(w, h, "".join(b))


# ------------------------------------------- кнопка «скачать» (560 px)
def btn_download():
    w, h = 560, 96
    t1, t2 = "СКАЧАТЬ RPChatOverlay.exe", "37,4 МБ · Windows 10/11 x64 · без установки"
    s1 = fit(t1, 400, 22, bold=True, spacing=0.7)
    s2 = fit(t2, 396, 13)
    b = [f'<rect x="3" y="3" width="{w-6}" height="{h-6}" rx="15" fill="#0b1a12" stroke="#2b7d51"/>',
         f'<rect x="7" y="7" width="{w-14}" height="{h-14}" rx="12" fill="url(#green)"/>',
         '<g transform="translate(26,26)"><path d="M18 1v20" stroke="#08220f" stroke-width="5" '
         'stroke-linecap="round"/><path d="M8 14l10 10 10-10" fill="none" stroke="#08220f" '
         'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
         '<path d="M3 30h30" stroke="#08220f" stroke-width="5" stroke-linecap="round"/></g>',
         f'<text x="84" y="48" font-size="{s1}" font-weight="bold" fill="#08220f" '
         f'letter-spacing="0.7">{t1}</text>',
         f'<text x="86" y="73" font-size="{s2}" fill="#0a3016" opacity="0.9">{t2}</text>']
    return svg(w, h, "".join(b))


# ------------------------------------------ кнопка «исходники» (560 px)
def btn_source():
    w, h = 560, 74
    t1, t2 = "ИСХОДНИКИ НА GITHUB", "папка source · Python 3.12 + PySide6"
    b = [f'<rect x="3" y="3" width="{w-6}" height="{h-6}" rx="13" fill="#171b24" stroke="{BLUE}" stroke-width="2"/>',
         f'<text x="38" y="46" font-size="21" font-weight="bold" fill="{BLUE}" text-anchor="middle">{{ }}</text>',
         f'<text x="68" y="36" font-size="{fit(t1, 460, 19, True, 0.5)}" font-weight="bold" '
         f'fill="{TXT}">{t1}</text>',
         f'<text x="70" y="58" font-size="{fit(t2, 460, 13)}" fill="{MUT}">{t2}</text>']
    return svg(w, h, "".join(b))


# -------------------------------------------------- бейдж VirusTotal (440 px)
def badge():
    w, h = 440, 70
    t1, t2 = "VirusTotal: 2 / 70", "Bkav и SecureAge — известные ложные"
    b = [f'<rect width="{w}" height="{h}" rx="12" fill="{PANEL}" stroke="{BORDER}"/>',
         f'<rect x="0" y="0" width="6" height="{h}" rx="3" fill="{GREEN}"/>',
         f'<text x="22" y="32" font-size="{fit(t1, 390, 18, True)}" font-weight="bold" '
         f'fill="{GREEN}">{t1}</text>',
         f'<text x="22" y="54" font-size="{fit(t2, 400, 12.5)}" fill="{MUT}">{t2}</text>']
    return svg(w, h, "".join(b))


if __name__ == "__main__":
    print("рендер (компактный набор):")
    render("sm_header", header())
    render("sm_features", section("sm_features", "ВОЗМОЖНОСТИ", "всё в интерфейсе", GREEN, "2"))
    render("sm_download", section("sm_download", "СКАЧАТЬ", "бесплатно", GREEN, "↓"))
    render("sm_note", section("sm_note", "ПРОВЕРКА ФАЙЛА", "VirusTotal", "#e0705c", "!"))
    render("sm_btn_download", btn_download())
    render("sm_btn_source", btn_source())
    render("sm_badge", badge())
