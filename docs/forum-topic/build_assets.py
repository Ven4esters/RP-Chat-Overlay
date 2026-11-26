"""Create the original, web-ready forum banner and section plates.

Run from the package root with Pillow installed:
    python forum-topic/build_assets.py
Output sizes follow the supplied Invision BBCode guide exactly.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets"
OUT.mkdir(parents=True, exist_ok=True)
S = 2
BG = (8, 19, 34)
PANEL = (17, 31, 51)
PANEL_2 = (23, 42, 67)
BLUE = (50, 153, 242)
BLUE_DARK = (30, 58, 110)
GREEN = (111, 168, 44)
LIME = (214, 232, 106)
WHITE = (242, 247, 252)
MUTED = (166, 184, 204)
LINE = (58, 77, 101)
FONT_PAIRS = (
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
)
FONTS = next(
    (
        (regular, bold)
        for regular, bold in FONT_PAIRS
        if Path(regular).is_file() and Path(bold).is_file()
    ),
    None,
)
if FONTS is None:
    raise RuntimeError(
        "Install a Unicode font (DejaVu Sans, Arial, or Segoe UI) to build the forum artwork"
    )


def font(size, bold=False):
    return ImageFont.truetype(FONTS[1 if bold else 0], size * S)


def text(draw, xy, value, size, fill, bold=False, anchor=None):
    draw.text((xy[0] * S, xy[1] * S), value, font=font(size, bold), fill=fill, anchor=anchor)


def roundrect(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(
        tuple(int(v * S) for v in box),
        radius=radius * S,
        fill=fill,
        outline=outline,
        width=width * S,
    )


def make_banner():
    w, h = 1200, 500
    im = Image.new("RGB", (w * S, h * S), BG)
    d = ImageDraw.Draw(im)
    # subtle blue atmosphere and fine grid, deliberately restrained for mobile crop
    for x in range(w * S):
        t = x / (w * S - 1)
        components = [
            round(a * (1 - t) + b * t) for a, b in zip((9, 20, 36), (13, 35, 54), strict=False)
        ]
        c = tuple(components)
        d.line((x, 0, x, h * S), fill=c)
    for x in range(25, w, 48):
        d.line((x * S, 0, x * S, h * S), fill=(18, 34, 52), width=1)
    for y in range(22, h, 48):
        d.line((0, y * S, w * S, y * S), fill=(18, 34, 52), width=1)
    # halo rings at the edge
    d.ellipse((850 * S, -150 * S, 1320 * S, 320 * S), outline=(28, 64, 101), width=2 * S)
    d.ellipse((890 * S, -110 * S, 1280 * S, 280 * S), outline=(25, 54, 85), width=1 * S)
    # left accent and branding
    roundrect(d, (62, 64, 71, 126), 4, GREEN)
    text(d, (92, 67), "FiveM Chat Overlay", 52, WHITE, True)
    text(d, (94, 145), "РОЛЕВОЙ ЧАТ — ПОНЯТНО НА ЛЮБОМ ЯЗЫКЕ", 18, LIME, True)
    text(d, (94, 188), "Перевод сообщений и правила анимаций для GTA V / FiveM", 18, MUTED)
    # keycaps / dynamic defaults (clearly labelled as editable defaults)
    roundrect(d, (94, 243, 172, 294), 12, PANEL_2, (57, 102, 151), 1)
    text(d, (133, 268), "T", 24, WHITE, True, "mm")
    text(d, (185, 273), "игровой чат", 16, MUTED)
    roundrect(d, (326, 243, 414, 294), 12, PANEL_2, (57, 102, 151), 1)
    text(d, (370, 268), "F6", 22, WHITE, True, "mm")
    text(d, (428, 273), "окно оверлея", 16, MUTED)
    text(d, (94, 323), "Клавиши — настраиваемые значения по умолчанию", 14, (133, 157, 182))
    # abstract app card, no game artwork or third-party branding
    roundrect(d, (700, 78, 1123, 408), 22, (7, 17, 31), (52, 93, 137), 2)
    roundrect(d, (700, 78, 1123, 126), 22, (19, 39, 65), None)
    d.rectangle((700 * S, 104 * S, 1123 * S, 126 * S), fill=(19, 39, 65))
    for i, c in enumerate((BLUE, GREEN, LIME)):
        d.ellipse(((726 + i * 24) * S, 96 * S, (738 + i * 24) * S, 108 * S), fill=c)
    text(d, (827, 102), "ПОДГОТОВКА СООБЩЕНИЯ", 13, MUTED, True, "lm")
    roundrect(d, (728, 151, 1095, 218), 13, (13, 29, 48), (39, 63, 89), 1)
    text(d, (750, 170), "Could you help me?", 17, WHITE)
    text(d, (750, 197), "Перевод перед отправкой", 12, MUTED)
    # translation card
    roundrect(d, (762, 239, 1095, 317), 15, (16, 45, 68), (42, 113, 155), 1)
    text(d, (784, 260), "Можешь мне помочь?", 17, WHITE, True)
    text(d, (784, 290), "проверяете текст → Enter", 12, (127, 201, 232))
    # bright action pill
    roundrect(d, (944, 344, 1095, 382), 18, (32, 115, 178), None)
    text(d, (1019, 363), "ГОТОВО К ИГРЕ", 12, WHITE, True, "mm")
    # footer rule
    d.line((94 * S, 446 * S, 1123 * S, 446 * S), fill=(39, 59, 81), width=1 * S)
    text(d, (94, 468), "Windows 10/11  ·  интерфейс RU / EN  ·  открытый исходный код", 13, MUTED)
    im.resize((w, h), Image.Resampling.LANCZOS).save(
        OUT / "banner-fivem-chat-overlay.png", optimize=True
    )


SECTIONS = [
    ("01", "О проекте"),
    ("02", "Возможности"),
    ("03", "Перевод и игровой чат"),
    ("04", "Правила и анимации"),
    ("05", "Установка и первый запуск"),
    ("06", "Настройки и горячие клавиши"),
    ("07", "Приватность и безопасность"),
    ("08", "Скачать и проверить"),
    ("09", "Поддержка и обратная связь"),
]


def make_plate(number, title):
    w, h = 1200, 62
    im = Image.new("RGB", (w * S, h * S), (16, 27, 43))
    d = ImageDraw.Draw(im)
    # subtle outline / full width keeps the strip usable without BBCode centering
    d.line((0, 0, w * S, 0), fill=(40, 55, 75), width=S)
    d.line((0, (h - 1) * S, w * S, (h - 1) * S), fill=(40, 55, 75), width=S)
    roundrect(d, (22, 11, 28, 51), 3, GREEN)
    text(d, (53, 31), number, 22, BLUE, True, "lm")
    text(d, (103, 31), title, 22, WHITE, True, "lm")
    # guide's soft trail line after heading
    box = d.textbbox((103 * S, 0), title, font=font(22, True))
    title_right = box[2] / S
    x0 = min(1160, max(title_right + 30, 360))
    if x0 < 1170:
        d.line((int(x0 * S), 31 * S, 1175 * S, 31 * S), fill=(49, 67, 88), width=1 * S)
    im.resize((w, h), Image.Resampling.LANCZOS).save(OUT / f"section-{number}.png", optimize=True)


if __name__ == "__main__":
    make_banner()
    for no, title in SECTIONS:
        make_plate(no, title)
    print(f"created 1 banner + {len(SECTIONS)} section plates in {OUT}")
