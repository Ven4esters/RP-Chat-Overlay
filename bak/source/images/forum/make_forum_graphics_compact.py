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


# ------------------------------------------------------- шапка (480 px)
def header():
    w, h = 480, 120
    b = [f'<rect width="{w}" height="{h}" fill="url(#bg)"/>',
         f'<rect width="{w}" height="{h}" fill="url(#grid)"/>',
         '<circle cx="450" cy="0" r="90" fill="#3d6fd8" opacity="0.10"/>',
         f'<rect x="0" y="{h-4}" width="{w}" height="4" fill="url(#bar)"/>',
         '<rect x="26" y="26" width="56" height="56" rx="14" fill="url(#logo)"/>',
         '<text x="54" y="64" font-size="24" font-weight="bold" fill="#0d1018" '
         'text-anchor="middle">RP</text>']
    title = "RP Chat Overlay"
    b.append(f'<text x="96" y="54" font-size="{fit(title, 360, 26, True)}" font-weight="bold" '
             f'fill="{TXT}">{title}</text>')
    sub = "переводчик чата для GTA V / FiveM"
    b.append(f'<text x="97" y="76" font-size="{fit(sub, 360, 14)}" fill="{MUT}">{sub}</text>')
    src, dst = "Слушай, брат", "Senti, fratello"
    ax = int(26 + measure(src, 12) + 10)
    b.append(f'<text x="26" y="104" font-size="12" fill="{DIM}">{src}</text>')
    b.append(f'<path d="M{ax} 100h14" stroke="{GREEN}" stroke-width="2"/>')
    b.append(f'<path d="M{ax+11} 96l6 4-6 4z" fill="{GREEN}"/>')
    b.append(f'<text x="{ax+24}" y="104" font-size="12" fill="#9fe3b5">{dst}</text>')
    return svg(w, h, "".join(b))


# --------------------------------------------- заголовок раздела (680 px)
def section(name, title, caption="", color=BLUE, icon="›"):
    w, h = 480, 46
    ts = fit(title, 260 if caption else 360, 16, bold=True, spacing=0.8)
    b = [f'<rect width="{w}" height="{h}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
         f'<rect x="0" y="0" width="6" height="{h}" rx="3" fill="{color}"/>',
         f'<circle cx="32" cy="{h/2}" r="12" fill="{color}" opacity="0.18"/>',
         f'<text x="32" y="{h/2+5}" font-size="14" font-weight="bold" fill="{color}" '
         f'text-anchor="middle">{icon}</text>',
         f'<text x="54" y="{h/2+5}" font-size="{ts}" font-weight="bold" fill="{TXT}" '
         f'letter-spacing="0.9">{title}</text>']
    if caption:
        b.append(f'<text x="{w-14}" y="{h/2+4}" font-size="{fit(caption, 130, 11)}" '
                 f'fill="{MUT}" text-anchor="end">{caption}</text>')
    return svg(w, h, "".join(b))


# ------------------------------------------- кнопка «скачать» (480 px)
def btn_download():
    w, h = 480, 84
    t1, t2 = "СКАЧАТЬ RPChatOverlay.exe", "37,4 МБ · Windows 10/11 · без установки"
    s1 = fit(t1, 340, 19, bold=True, spacing=0.6)
    s2 = fit(t2, 336, 12)
    b = [f'<rect x="3" y="3" width="{w-6}" height="{h-6}" rx="13" fill="#0b1a12" stroke="#2b7d51"/>',
         f'<rect x="6" y="6" width="{w-12}" height="{h-12}" rx="10" fill="url(#green)"/>',
         '<g transform="translate(22,22)"><path d="M15 1v17" stroke="#08220f" stroke-width="4.5" '
         'stroke-linecap="round"/><path d="M7 12l8 8 8-8" fill="none" stroke="#08220f" '
         'stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>'
         '<path d="M3 26h25" stroke="#08220f" stroke-width="4.5" stroke-linecap="round"/></g>',
         f'<text x="72" y="42" font-size="{s1}" font-weight="bold" fill="#08220f" '
         f'letter-spacing="0.6">{t1}</text>',
         f'<text x="74" y="64" font-size="{s2}" fill="#0a3016" opacity="0.9">{t2}</text>']
    return svg(w, h, "".join(b))


# ------------------------------------------ кнопка «исходники» (480 px)
def btn_source():
    w, h = 480, 64
    t1, t2 = "ИСХОДНИКИ НА GITHUB", "папка source · Python 3.12 + PySide6"
    b = [f'<rect x="3" y="3" width="{w-6}" height="{h-6}" rx="12" fill="#171b24" stroke="{BLUE}" stroke-width="2"/>',
         f'<text x="34" y="40" font-size="18" font-weight="bold" fill="{BLUE}" text-anchor="middle">{{ }}</text>',
         f'<text x="62" y="30" font-size="{fit(t1, 390, 17, True, 0.4)}" font-weight="bold" '
         f'fill="{TXT}">{t1}</text>',
         f'<text x="64" y="50" font-size="{fit(t2, 390, 12)}" fill="{MUT}">{t2}</text>']
    return svg(w, h, "".join(b))


# -------------------------------------------------- бейдж VirusTotal (360 px)
def badge():
    w, h = 360, 60
    t1, t2 = "VirusTotal: 2 / 70", "Bkav и SecureAge — ложные"
    b = [f'<rect width="{w}" height="{h}" rx="11" fill="{PANEL}" stroke="{BORDER}"/>',
         f'<rect x="0" y="0" width="5" height="{h}" rx="2.5" fill="{GREEN}"/>',
         f'<text x="18" y="28" font-size="{fit(t1, 320, 16, True)}" font-weight="bold" '
         f'fill="{GREEN}">{t1}</text>',
         f'<text x="18" y="47" font-size="{fit(t2, 330, 11.5)}" fill="{MUT}">{t2}</text>']
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
