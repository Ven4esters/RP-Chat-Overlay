#!/usr/bin/env python3
"""Генерация изображений-заголовков для README в стиле форума (PIL).

Стиль: тёмная панель #191d26, обводка #2b3140, акцентная полоса слева
(синий→зелёный градиент), белый текст #f2f4f8, размер 720×48, шрифт 17.
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).parent
W, H = 720, 48
PANEL = (0x19, 0x1D, 0x26)
BORDER = (0x2B, 0x31, 0x40)
TXT = (0xF2, 0xF4, 0xF8)
BLUE = (0x3D, 0x6F, 0xD8)
GREEN = (0x57, 0xC9, 0x8A)
BAR_W = 4
BAR_H = 20
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def fit_size(text, max_w, size, bold=True):
    font = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    while size > 8 and font.getlength(text) > max_w:
        size -= 1
        font = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    return size, font


def make_accent_bar(h):
    """Вертикальный градиент синий→зелёный."""
    bar = Image.new("RGB", (BAR_W, h), (0, 0, 0))
    draw = ImageDraw.Draw(bar)
    for y in range(h):
        t = y / (h - 1) if h > 1 else 0
        r = int(BLUE[0] + (GREEN[0] - BLUE[0]) * t)
        g = int(BLUE[1] + (GREEN[1] - BLUE[1]) * t)
        b = int(BLUE[2] + (GREEN[2] - BLUE[2]) * t)
        draw.line([(0, y), (BAR_W - 1, y)], fill=(r, g, b))
    return bar


def head(name, text):
    img = Image.new("RGB", (W, H), PANEL)
    draw = ImageDraw.Draw(img)

    # обводка (скруглённый прямоугольник через обводку по краям)
    draw.rectangle([0, 0, W - 1, H - 1], outline=BORDER, width=2)

    # акцентная полоса слева
    bar_y = (H - BAR_H) // 2
    bar = make_accent_bar(BAR_H)
    img.paste(bar, (14, bar_y))

    # текст — центрируем по вертикали через anchor="lm" (left, middle),
    # как на эталонном изображении "Что умеет программа"
    max_w = W - 2 * 14 - BAR_W - 13 - 10
    size, font = fit_size(text, max_w, 17, bold=True)
    draw.text((14 + BAR_W + 13, H / 2), text, font=font, fill=TXT,
              anchor="lm")

    out = OUT / f"{name}.png"
    img.save(out)
    print(f"  {out}  {img.size[0]}×{img.size[1]}")


if __name__ == "__main__":
    # Все изображения единого размера 720×48, шрифт 17, текст центрирован anchor="lm"
    RU = [
        ("hdr_contents_ru", "Содержание"),
        ("hdr_about_ru", "О проекте"),
        ("hdr_stack_ru", "Стек технологий"),
        ("hdr_requirements_ru", "Требования"),
        ("hdr_installation_ru", "Установка"),
        ("hdr_quickstart_ru", "Быстрый старт"),
        ("hdr_configuration_ru", "Конфигурация"),
        ("hdr_modes_ru", "Режимы перевода и спецсимволы"),
        ("hdr_deeplx_ru", "DeepLX в России"),
        ("hdr_license_ru", "Лицензия"),
        ("hdr_contacts_ru", "Контакты"),
    ]
    EN = [
        ("hdr_contents_en", "Contents"),
        ("hdr_about_en", "About the project"),
        ("hdr_stack_en", "Tech stack"),
        ("hdr_requirements_en", "Requirements"),
        ("hdr_installation_en", "Installation"),
        ("hdr_quickstart_en", "Quick start"),
        ("hdr_configuration_en", "Configuration"),
        ("hdr_modes_en", "Translation modes and special symbols"),
        ("hdr_deeplx_en", "DeepLX in Russia"),
        ("hdr_license_en", "License"),
        ("hdr_contacts_en", "Contacts"),
    ]
    print("генерируем RU заголовки:")
    for n, t in RU:
        head(n, t)
    print("генерируем EN заголовки:")
    for n, t in EN:
        head(n, t)
