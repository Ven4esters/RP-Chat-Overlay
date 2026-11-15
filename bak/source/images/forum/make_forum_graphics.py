#!/usr/bin/env python3
"""Генерация графики для темы на форуме: баннер, заголовки разделов, кнопки скачивания.
SVG -> PNG через cairosvg. Палитра совпадает с картинками в source/images/."""
import pathlib
import cairosvg
from PIL import ImageFont

_F = {False: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
      True: "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"}


def measure(text, size, bold=False, spacing=0.0):
    """Ширина строки в пикселях — по тем же метрикам, что использует рендер."""
    f = ImageFont.truetype(_F[bold], int(size))
    return f.getlength(text) + spacing * max(0, len(text) - 1)


def fit(text, max_w, size, bold=False, spacing=0.0, min_size=10):
    """Подобрать размер шрифта, чтобы строка влезла в max_w."""
    while size > min_size and measure(text, size, bold, spacing) > max_w:
        size -= 1
    return size


OUT = pathlib.Path(__file__).parent
BG, PANEL, BORDER = "#12141b", "#1a1d26", "#2b3040"
TXT, DIM, MUT = "#f2f4f8", "#b9c0d4", "#78829a"
BLUE, GREEN, GOLD = "#3d6fd8", "#57c98a", "#ffcf5c"
FONT = "DejaVu Sans, Segoe UI, Roboto, Arial, sans-serif"

DEFS = f'''
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0e1017"/><stop offset="0.55" stop-color="#151824"/>
    <stop offset="1" stop-color="#0f1319"/>
  </linearGradient>
  <linearGradient id="logo" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/>
  </linearGradient>
  <linearGradient id="green" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#2fa364"/><stop offset="1" stop-color="#6fdd9b"/>
  </linearGradient>
  <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/>
  </linearGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{BLUE}" stop-opacity="0.30"/>
    <stop offset="1" stop-color="{BLUE}" stop-opacity="0"/>
  </linearGradient>
  <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
    <path d="M40 0H0V40" fill="none" stroke="#ffffff" stroke-opacity="0.035"/>
  </pattern>
</defs>'''


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{FONT}">{DEFS}{body}</svg>')


def render(name, text, scale=2):
    (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
    cairosvg.svg2png(bytestring=text.encode(), write_to=str(OUT / f"{name}.png"), scale=scale)
    print(f"  {name}.png  {w_ok(name)}")


def w_ok(name):
    p = OUT / f"{name}.png"
    return f"{(p.stat().st_size / 1024):.0f} КБ"


# ---------------------------------------------------------------- 1. БАННЕР
def header():
    w, h = 1200, 380
    b = [f'<rect ss="0" width="{w}" height="{h}" fill="url(#bg)"/>',
         f'<rect width="{w}" height="{h}" fill="url(#grid)"/>',
         '<circle cx="1100" cy="20" r="230" fill="#3d6fd8" opacity="0.10"/>',
         '<circle cx="60" cy="360" r="180" fill="#57c98a" opacity="0.08"/>',
         f'<rect x="0" y="{h-6}" width="{w}" height="6" fill="url(#bar)"/>']

    # логотип
    b.append('<rect x="64" y="58" width="104" height="104" rx="26" fill="url(#logo)"/>')
    b.append('<text x="116" y="130" font-size="44" font-weight="bold" fill="#0d1018" '
             'text-anchor="middle">RP</text>')

    # заголовок
    b.append(f'<text x="196" y="106" font-size="52" font-weight="bold" fill="{TXT}" '
             'letter-spacing="0.5">RP Chat Overlay</text>')
    b.append(f'<text x="198" y="148" font-size="25" fill="{MUT}">'
             'переводчик чата для GTA V / FiveM</text>')

    # чипы
    chips = ["13 языков", "свои словари", "слова-паразиты", "Windows 10/11", "открытый код"]
    x = 198
    widths = {"13 языков": 128, "свои словари": 158, "слова-паразиты": 186,
              "Windows 10/11": 168, "открытый код": 166}
    for c in chips:
        cw = widths[c]
        b.append(f'<rect x="{x}" y="176" width="{cw}" height="40" rx="20" '
                 f'fill="#1c2029" stroke="{BORDER}"/>')
        b.append(f'<text x="{x + cw/2}" y="202" font-size="17" fill="{DIM}" '
                 f'text-anchor="middle">{c}</text>')
        x += cw + 10

    # пример перевода: два «сообщения»
    b.append(f'<rect x="700" y="238" width="440" height="0" fill="none"/>')
    # левое (RU)
    b.append(f'<rect x="66" y="248" width="470" height="86" rx="14" fill="#1a1e28" '
             f'stroke="{BORDER}"/>')
    b.append(f'<text x="88" y="278" font-size="15" fill="{MUT}">вы печатаете</text>')
    b.append(f'<text x="88" y="312" font-size="24" fill="{TXT}">Слушай, брат, подожди</text>')
    # стрелка
    b.append(f'<path d="M556 291h44" stroke="{GREEN}" stroke-width="3"/>')
    b.append(f'<path d="M592 283l10 8-10 8z" fill="{GREEN}"/>')
    # правое (IT)
    b.append(f'<rect x="616" y="248" width="518" height="86" rx="14" fill="#16251d" '
             f'stroke="#2e6b48"/>')
    b.append(f'<text x="638" y="278" font-size="15" fill="#7fc79f">видит итальянец</text>')
    b.append(f'<text x="638" y="312" font-size="24" fill="#d8f7e4">Senti, fratello, aspetta</text>')
    return svg(w, h, "".join(b))


# ------------------------------------------------- 2. ЗАГОЛОВКИ РАЗДЕЛОВ
def section(name, title, caption="", color=BLUE, icon="›"):
    w, h = 900, 84
    ts = fit(title, 560 if caption else 760, 27, bold=True, spacing=1.2)
    b = [f'<rect width="{w}" height="{h}" rx="14" fill="{PANEL}" stroke="{BORDER}"/>',
         f'<rect x="0" y="0" width="8" height="{h}" rx="4" fill="{color}"/>',
         f'<rect x="8" y="0" width="180" height="{h}" fill="url(#fade)"/>',
         f'<circle cx="56" cy="{h/2}" r="20" fill="{color}" opacity="0.18"/>',
         f'<text x="56" y="{h/2 + 8}" font-size="24" font-weight="bold" fill="{color}" '
         f'text-anchor="middle">{icon}</text>',
         f'<text x="94" y="{h/2 + 10}" font-size="{ts}" font-weight="bold" fill="{TXT}" '
         f'letter-spacing="1.2">{title}</text>']
    if caption:
        b.append(f'<text x="{w-28}" y="{h/2 + 6}" font-size="16" fill="{MUT}" '
                 f'text-anchor="end">{caption}</text>')
    return svg(w, h, "".join(b))


# ---------------------------------------------------------- 3. КНОПКИ
def btn_download():
    w, h = 760, 156
    t1, t2 = "СКАЧАТЬ", "RPChatOverlay.exe · 37,4 МБ · Windows 10/11 x64"
    s1 = fit(t1, 560, 46, bold=True, spacing=1.5)
    s2 = fit(t2, 566, 21)
    b = [f'<rect x="6" y="6" width="{w-12}" height="{h-12}" rx="22" fill="#0b1a12" '
         f'stroke="#2b7d51" opacity="0.9"/>',
         f'<rect x="10" y="10" width="{w-20}" height="{h-20}" rx="20" fill="url(#green)"/>',
         f'<g transform="translate(44,42)">'
         f'<path d="M30 2v32" stroke="#08220f" stroke-width="7" stroke-linecap="round"/>'
         f'<path d="M14 22l16 16 16-16" fill="none" stroke="#08220f" stroke-width="7" '
         f'stroke-linecap="round" stroke-linejoin="round"/>'
         f'<path d="M6 48h48" stroke="#08220f" stroke-width="7" stroke-linecap="round"/></g>',
         f'<text x="128" y="78" font-size="{s1}" font-weight="bold" fill="#08220f" '
         f'letter-spacing="1.5">{t1}</text>',
         f'<text x="130" y="114" font-size="{s2}" fill="#0a3016" opacity="0.9">{t2}</text>']
    return svg(w, h, "".join(b))


def btn_source():
    w, h = 760, 116
    t1, t2 = "ИСХОДНИКИ НА GITHUB", "папка source · Python 3.12 + PySide6 · сборка своими руками"
    s1 = fit(t1, 596, 28, bold=True, spacing=0.8)
    s2 = fit(t2, 600, 18)
    b = [f'<rect x="6" y="6" width="{w-12}" height="{h-12}" rx="18" fill="#171b24" '
         f'stroke="{BLUE}" stroke-width="2"/>',
         f'<rect x="10" y="10" width="{w-20}" height="{h-20}" rx="14" fill="url(#fade)"/>',
         f'<text x="56" y="72" font-size="32" font-weight="bold" fill="{BLUE}" '
         f'text-anchor="middle">{{ }}</text>',
         f'<text x="100" y="60" font-size="{s1}" font-weight="bold" fill="{TXT}" '
         f'letter-spacing="0.8">{t1}</text>',
         f'<text x="102" y="90" font-size="{s2}" fill="{MUT}">{t2}</text>']
    return svg(w, h, "".join(b))


def badge(name, text, caption, color=GREEN):
    w, h = 560, 96
    b = [f'<rect width="{w}" height="{h}" rx="16" fill="{PANEL}" stroke="{BORDER}"/>',
         f'<rect x="0" y="0" width="8" height="{h}" rx="4" fill="{color}"/>',
         f'<text x="34" y="44" font-size="{fit(text, 490, 22, bold=True)}" '
         f'font-weight="bold" fill="{color}">{text}</text>',
         f'<text x="34" y="74" font-size="{fit(caption, 500, 16)}" fill="{MUT}">{caption}</text>']
    return svg(w, h, "".join(b))


if __name__ == "__main__":
    print("рендер:")
    render("header", header())
    render("sec_how", section("sec_how", "КАК ПОЛЬЗОВАТЬСЯ", "3 шага", BLUE, "1"))
    render("sec_features", section("sec_features", "ВОЗМОЖНОСТИ", "", GREEN, "2"))
    render("sec_langs", section("sec_langs", "ЯЗЫКИ СЕРВЕРОВ", "13 направлений", GOLD, "3"))
    render("sec_download", section("sec_download", "СКАЧАТЬ", "бесплатно, без регистрации", GREEN, "↓"))
    render("sec_note", section("sec_note", "ВАЖНО ЗНАТЬ", "антивирус и проверка файла", "#e0705c", "!"))
    render("btn_download", btn_download())
    render("btn_source", btn_source())
    render("badge_clean", badge("badge_clean", "VirusTotal: 2 / 70",
                                "Bkav и SecureAge — известные ложные срабатывания", GREEN))
