#!/usr/bin/env python3
"""Generate English and Russian README headers in their respective reference styles.

English headers use the large rectangular reference (1000×150).
Russian headers use the compact rounded reference (720×48).
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).parent
PANEL = (0x19, 0x1D, 0x26)
BORDER = (0x2B, 0x31, 0x40)
TXT = (0xF2, 0xF4, 0xF8)
BLUE = (0x3D, 0x6F, 0xD8)
GREEN = (0x57, 0xC9, 0x8A)
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def fit_size(text, max_w, size):
    font = ImageFont.truetype(FONT_BOLD, size)
    while size > 10 and font.getlength(text) > max_w:
        size -= 1
        font = ImageFont.truetype(FONT_BOLD, size)
    return font


def gradient_bar(width, height, rounded=False):
    """Create a vertical blue-to-green accent bar."""
    bar = Image.new("RGB", (width, height), BLUE)
    pixels = bar.load()
    for y in range(height):
        t = y / (height - 1) if height > 1 else 0
        color = tuple(round(a + (b - a) * t) for a, b in zip(BLUE, GREEN))
        for x in range(width):
            pixels[x, y] = color
    if not rounded:
        return bar, None

    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=width // 2, fill=255
    )
    return bar, mask


def head_ru(name, text):
    """Render compact rounded 720×48 Russian heading like the RU reference."""
    width, height = 720, 48
    img = Image.new("RGB", (width, height), (0x1C, 0x20, 0x2A))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=10,
        fill=(0x1C, 0x20, 0x2A), outline=BORDER, width=1
    )

    bar, mask = gradient_bar(4, 20, rounded=True)
    img.paste(bar, (14, (height - 20) // 2), mask)
    text_x = 38
    font = fit_size(text, width - text_x - 20, 17)
    draw.text((text_x, height / 2), text, font=font, fill=TXT, anchor="lm")
    img.save(OUT / f"{name}.png")
    print(f"  {name}.png: 720×48")


def head_en(name, text):
    """Render large rectangular 1000×150 English heading like the EN reference."""
    width, height = 1000, 150
    img = Image.new("RGB", (width, height), PANEL)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, height - 1), outline=BORDER, width=2)

    bar, _ = gradient_bar(8, 80)
    img.paste(bar, (20, (height - 80) // 2))
    text_x = 50
    font = fit_size(text, width - text_x - 24, 36)
    draw.text((text_x, height / 2), text, font=font, fill=TXT, anchor="lm")
    img.save(OUT / f"{name}.png")
    print(f"  {name}.png: 1000×150")


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
        head_ru(name, text)
    print("Generating English headings:")
    for name, text in EN:
        head_en(name, text)
