#!/usr/bin/env python3
"""Generate bilingual README heading images matching the compact reference pill.

Размер и оформление соответствуют эталонной плашке: 720×48, скруглённый
тёмный фон, тонкая синевато-зелёная полоса слева и жирный текст по центру.
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).parent
W, H = 720, 48
PANEL = (0x1C, 0x20, 0x2A)
BORDER = (0x2B, 0x31, 0x40)
TXT = (0xF2, 0xF4, 0xF8)
BLUE = (0x3D, 0x6F, 0xD8)
GREEN = (0x57, 0xC9, 0x8A)
BAR_W = 4
BAR_H = 20
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def fit_size(text, max_w, size):
    font = ImageFont.truetype(FONT_BOLD, size)
    while size > 10 and font.getlength(text) > max_w:
        size -= 1
        font = ImageFont.truetype(FONT_BOLD, size)
    return font


def make_accent_bar():
    """Create a rounded vertical blue-to-green gradient accent."""
    bar = Image.new("RGB", (BAR_W, BAR_H), BLUE)
    pixels = bar.load()
    for y in range(BAR_H):
        t = y / (BAR_H - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(BLUE, GREEN))
        for x in range(BAR_W):
            pixels[x, y] = color

    mask = Image.new("L", (BAR_W, BAR_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, BAR_W - 1, BAR_H - 1), radius=BAR_W // 2, fill=255
    )
    return bar, mask


def head(name, text):
    img = Image.new("RGB", (W, H), PANEL)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, W - 1, H - 1), radius=10, fill=PANEL, outline=BORDER, width=1
    )

    bar, mask = make_accent_bar()
    bar_y = (H - BAR_H) // 2
    img.paste(bar, (14, bar_y), mask)

    text_x = 14 + BAR_W + 20
    font = fit_size(text, W - text_x - 20, 17)
    draw.text((text_x, H / 2), text, font=font, fill=TXT, anchor="lm")

    out = OUT / f"{name}.png"
    img.save(out)
    print(f"  {out.name}: {W}×{H}")


if __name__ == "__main__":
    RU = [
        ("hdr_contents_ru", "Содержание"),
        ("hdr_about_ru", "О проекте"),
        ("hdr_features_ru", "Что умеет программа"),
        ("hdr_stack_ru", "Стек технологий"),
        ("hdr_requirements_ru", "Требования"),
        ("hdr_installation_ru", "Установка"),
        ("hdr_configuration_ru", "Настройки"),
        ("hdr_modes_ru", "Режимы перевода и спецсимволы"),
        ("hdr_deeplx_ru", "DeepLX в России"),
        ("hdr_license_ru", "Лицензия"),
        ("hdr_contacts_ru", "Контакты"),
    ]
    EN = [
        ("hdr_contents_en", "Contents"),
        ("hdr_about_en", "About the project"),
        ("hdr_features_en", "Features"),
        ("hdr_stack_en", "Tech stack"),
        ("hdr_requirements_en", "Requirements"),
        ("hdr_installation_en", "Installation"),
        ("hdr_configuration_en", "Settings"),
        ("hdr_modes_en", "Translation modes and special symbols"),
        ("hdr_deeplx_en", "DeepLX in Russia"),
        ("hdr_license_en", "License"),
        ("hdr_contacts_en", "Contacts"),
    ]
    print("Generating Russian headings:")
    for name, text in RU:
        head(name, text)
    print("Generating English headings:")
    for name, text in EN:
        head(name, text)
