"""Сборка ``icon.ico`` — иконка программы во всех нужных размерах.

Запуск из папки ``source``:
    python tools/make_icon.py

Почему рисунок разный по размерам: в 16 и 20 пикселей пузырь с двумя буквами
внутри превращается в кашу, поэтому там остаются только крупные белые буквы на
зелёной плитке. С 24 пикселей буквы внутри пузыря уже читаются, и иконка
возвращается к основному виду.

Why the drawing depends on the size: at 16 and 20 pixels a bubble with two
letters inside turns to mush, so those sizes keep just the big white letters on
the green tile. From 24 pixels on the letters inside the bubble read fine and
the main design comes back.
"""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GREEN = (46, 125, 50)          # #2e7d32 — фон плитки / the tile colour
GREEN_DARK = (27, 94, 32)      # #1b5e20 — буквы в пузыре / letters in the bubble
WHITE = (255, 255, 255)

# размеры, которые запрашивает Windows: заголовок окна, панель задач, Alt+Tab,
# проводник / the sizes Windows asks for: title bar, taskbar, Alt+Tab, Explorer
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

SS = 8                         # суперсэмплинг: рисуем крупно, уменьшаем ровно
FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",                 # Windows
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)


def _font(every_px: int) -> ImageFont.FreeTypeFont:
    """Жирный шрифт нужного кегля / the bold font at the given pixel size."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, every_px)
    return ImageFont.load_default(every_px)


def _fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
         limit: float) -> ImageFont.FreeTypeFont:
    """Уменьшать кегль, пока текст не влезет в limit пикселей / shrink to fit."""
    while True:
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        if right - left <= limit or font.size <= 8:
            return font
        step = max(1, font.size // 12)
        font = _font(font.size - step)


def _center(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
            cx: float, cy: float) -> tuple[float, float]:
    """Левый верхний угол для центрирования текста / top-left corner to centre."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return cx - (right - left) / 2 - left, cy - (bottom - top) / 2 - top


def tile(n: int) -> Image.Image:
    """Пустая зелёная плитка со скруглёнными углами / the empty green tile."""
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, n - 1, n - 1), radius=int(n * 0.22), fill=GREEN)
    return img


def render_bubble(size: int) -> Image.Image:
    """Основной вид: белый пузырь с зелёными буквами / the main look."""
    n = size * SS
    img = tile(n)
    draw = ImageDraw.Draw(img)

    left = 0.185 * n
    top = 0.195 * n
    width = n - 2 * left
    height = (n - 2 * top) * 0.665
    radius = n * 0.088
    draw.rounded_rectangle((left, top, left + width, top + height),
                           radius=radius, fill=WHITE)

    # хвостик вниз-влево, потолще: в мелком размере тонкий пропадает
    # the tail down-left, drawn thick: a thin one disappears when small
    tail = width * 0.30
    start = left + width * 0.22
    draw.polygon([(start, top + height - radius * 0.35),
                  (start + tail, top + height - radius * 0.35),
                  (start + tail * 0.50, top + height + n * 0.135)], fill=WHITE)

    font = _fit(draw, "RP", _font(int(height * 0.66 * 1.30)), width * 0.74)
    x, y = _center(draw, "RP", font, left + width / 2, top + height * 0.47)
    draw.text((x, y), "RP", font=font, fill=GREEN_DARK)
    return img.resize((size, size), Image.LANCZOS)


def render_letters(size: int) -> Image.Image:
    """Мелкий размер: только крупные буквы, пузыря нет / big letters only."""
    n = size * SS
    img = tile(n)
    draw = ImageDraw.Draw(img)
    font = _fit(draw, "RP", _font(int(n * 0.56)), n * 0.72)
    x, y = _center(draw, "RP", font, n / 2, n / 2)
    draw.text((x, y), "RP", font=font, fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def render(size: int) -> Image.Image:
    """Иконка нужного размера / the icon at the given size."""
    return render_letters(size) if size <= 20 else render_bubble(size)


def _dib(img: Image.Image) -> bytes:
    """Запись BMP для ICO: BGRA снизу вверх плюс маска прозрачности.

    The BMP entry for an ICO: BGRA bottom-up plus the transparency mask. Small
    entries stay uncompressed so every Windows version reads them the same way.
    """
    width, height = img.size
    pixels = img.load()
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            row += bytes((blue, green, red, alpha))
        rows.append(bytes(row))
    bitmap = b"".join(rows)

    stride = ((width + 31) // 32) * 4
    mask = bytearray()
    for y in range(height - 1, -1, -1):
        row = bytearray(stride)
        for x in range(width):
            if pixels[x, y][3] < 128:
                row[x // 8] |= 0x80 >> (x % 8)
        mask += row

    header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0,
                         len(bitmap) + len(mask), 0, 0, 0, 0)
    return header + bitmap + bytes(mask)


def write_ico(path: Path, images: dict[int, Image.Image]) -> None:
    """Собрать ICO: до 64 px — BMP, крупнее — PNG / build the ICO file."""
    entries, blobs = [], []
    for size in sorted(images):
        img = images[size].convert("RGBA")
        if size <= 64:
            payload = _dib(img)
        else:
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            payload = buffer.getvalue()
        blobs.append(payload)
        entries.append((size, len(payload)))

    offset = 6 + 16 * len(entries)
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    for (size, length), _payload in zip(entries, blobs):
        side = 0 if size >= 256 else size           # 256 записывается как 0
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, length, offset)
        offset += length
    for payload in blobs:
        out += payload
    path.write_bytes(bytes(out))


def build(target: Path, png: Path | None = None) -> Path:
    """Нарисовать все размеры и записать файл / draw every size and save.

    Рядом кладётся ``icon.png`` — картинка для README и темы на форуме.
    An ``icon.png`` goes next to it: the picture for the README and forum posts.
    """
    write_ico(target, {size: render(size) for size in SIZES})
    if png is not None:
        render_bubble(512).save(png, format="PNG", optimize=True)
    return target


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "icon.ico"
    png = out.with_suffix(".png")
    build(out, png)
    print(f"готово: {out} ({out.stat().st_size} байт, {len(SIZES)} размеров) "
          f"и {png.name}")
