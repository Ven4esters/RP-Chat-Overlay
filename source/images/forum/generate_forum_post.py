#!/usr/bin/env python3
"""Рисует двуязычную графику поста в тёмном стиле RP Overlay.

Только главный баннер центрирован; все заголовки разделов, включая «Что
нового?», выровнены влево. Таблицы сохраняются как PNG, поскольку форум
ненадёжно отображает BBCode-таблицы.

Generate bilingual forum-post artwork in the existing dark RP Overlay style.
Only the hero is centered; all section headers, including “What’s new?”, are
left-aligned. Tables are PNGs because the target forum does not render BBCode
tables reliably.

Требуется Pillow; запуск из корня проекта: `python source/images/forum/generate_forum_post.py`.
Requires Pillow; run from the project root with the command above.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
SCALE = 2
WIDTH = 720
BG = (14, 18, 27)
PANEL = (25, 30, 42)
PANEL_ALT = (30, 36, 50)
BORDER = (48, 58, 76)
TEXT = (241, 245, 251)
MUTED = (154, 166, 188)
GREEN = (88, 214, 157)
BLUE = (79, 145, 231)

FONT_REGULAR = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)
FONT_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
)


def font(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = FONT_BOLD if bold else FONT_REGULAR
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, round(size * SCALE))
    return ImageFont.load_default()


def save(image: Image.Image, name: str) -> None:
    image.resize((image.width // SCALE, image.height // SCALE), Image.Resampling.LANCZOS).save(
        OUT / name
    )
    print(f"{name}: {image.width // SCALE}×{image.height // SCALE}")


def centered_text(draw: ImageDraw.ImageDraw, xy, text, text_font, fill) -> None:
    draw.text(xy, text, font=text_font, fill=fill, anchor="mm")


def hero(name: str, locale: str) -> None:
    height = 188
    image = Image.new("RGB", (WIDTH * SCALE, height * SCALE), BG)
    draw = ImageDraw.Draw(image)
    w, h = image.size

    # Сдержанный сине-зелёный градиент, сетка и дуги по краям.
    # Restrained blue-to-green ambient gradient, grid, and corner rings.
    for x in range(w):
        t = x / max(1, w - 1)
        top = tuple(round(a * (1 - t) + b * t) for a, b in zip((15, 24, 39), (17, 37, 43)))
        draw.line((x, 0, x, h), fill=top)
    for x in range(0, w, 72 * SCALE):
        draw.line((x, 0, x, h), fill=(25, 35, 48), width=1)
    for y in range(0, h, 48 * SCALE):
        draw.line((0, y, w, y), fill=(25, 35, 48), width=1)
    draw.ellipse(
        (-118 * SCALE, -130 * SCALE, 180 * SCALE, 168 * SCALE),
        outline=(37, 74, 88),
        width=2 * SCALE,
    )
    draw.ellipse(
        (590 * SCALE, 8 * SCALE, 835 * SCALE, 253 * SCALE), outline=(36, 66, 82), width=2 * SCALE
    )

    # Декоративные речевые маркеры остаются за пределами области заголовка.
    # Decorative speech marks stay outside the title block.
    bubble_color = (73, 132, 147)
    draw.rounded_rectangle(
        (35 * SCALE, 76 * SCALE, 50 * SCALE, 91 * SCALE),
        radius=4 * SCALE,
        outline=bubble_color,
        width=2 * SCALE,
    )
    draw.polygon(
        [(42 * SCALE, 91 * SCALE), (39 * SCALE, 97 * SCALE), (48 * SCALE, 91 * SCALE)],
        fill=bubble_color,
    )
    draw.rounded_rectangle(
        (670 * SCALE, 83 * SCALE, 685 * SCALE, 98 * SCALE),
        radius=4 * SCALE,
        outline=bubble_color,
        width=2 * SCALE,
    )
    draw.polygon(
        [(678 * SCALE, 98 * SCALE), (675 * SCALE, 104 * SCALE), (684 * SCALE, 98 * SCALE)],
        fill=bubble_color,
    )

    badge = "GTA V  •  FIVEM" if locale == "en" else "GTA V  •  FIVEM"
    title = "RP Chat Overlay"
    subtitle = (
        "Chat translation and animation automation for roleplay"
        if locale == "en"
        else "Перевод чата и автоматизация анимаций для ролевой игры"
    )
    centered_text(draw, (w // 2, 42 * SCALE), badge, font(11, True), GREEN)
    centered_text(draw, (w // 2, 89 * SCALE), title, font(39, True), TEXT)
    centered_text(draw, (w // 2, 129 * SCALE), subtitle, font(15), MUTED)

    # Тонкая акцентная линия внизу / Fine bottom accent line.
    for x in range(w):
        t = x / max(1, w - 1)
        color = tuple(round(a * (1 - t) + b * t) for a, b in zip(BLUE, GREEN))
        draw.line((x, h - 4 * SCALE, x, h - 1), fill=color)
    save(image, name)


def whats_new_header(name: str, locale: str) -> None:
    title = "Что нового?" if locale == "ru" else "What’s new?"
    height = 62
    image = Image.new("RGB", (WIDTH * SCALE, height * SCALE), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (1 * SCALE, 1 * SCALE, (WIDTH - 2) * SCALE, (height - 2) * SCALE),
        radius=12 * SCALE,
        fill=PANEL,
        outline=BORDER,
        width=1 * SCALE,
    )
    draw.rounded_rectangle(
        (18 * SCALE, 14 * SCALE, 23 * SCALE, 48 * SCALE),
        radius=3 * SCALE,
        fill=GREEN,
    )
    title_font = font(19, True)
    title_x = 38 * SCALE
    title_y = 31 * SCALE
    draw.text((title_x, title_y), title, font=title_font, fill=TEXT, anchor="lm")
    line_start = title_x + int(draw.textlength(title, font=title_font)) + 18 * SCALE
    draw.line((line_start, title_y, 690 * SCALE, title_y), fill=BORDER, width=1 * SCALE)
    save(image, name)

def section(name: str, label: str, number: int) -> None:
    height = 62
    image = Image.new("RGB", (WIDTH * SCALE, height * SCALE), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (1 * SCALE, 1 * SCALE, (WIDTH - 2) * SCALE, (height - 2) * SCALE),
        radius=12 * SCALE,
        fill=PANEL,
        outline=BORDER,
        width=1 * SCALE,
    )
    draw.rounded_rectangle(
        (18 * SCALE, 14 * SCALE, 23 * SCALE, 48 * SCALE),
        radius=3 * SCALE,
        fill=GREEN,
    )
    draw.text(
        (38 * SCALE, 31 * SCALE), f"{number:02d}", font=font(11, True), fill=BLUE, anchor="lm"
    )
    draw.text((76 * SCALE, 31 * SCALE), label, font=font(19, True), fill=TEXT, anchor="lm")
    # Линия задаёт направление заголовка слева, не центрируя его.
    # A subtle line guides the left-aligned title without centering it.
    start = min(420 * SCALE, 80 * SCALE + int(draw.textlength(label, font=font(19, True))))
    draw.line((start, 31 * SCALE, 690 * SCALE, 31 * SCALE), fill=BORDER, width=1 * SCALE)
    save(image, name)


def wrap(text: str, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or probe.textlength(candidate, font=text_font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def table(name: str, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
    pad = 16
    header_font = font(13, True)
    cell_font = font(13)
    line_height = 18 * SCALE
    header_height = 42 * SCALE
    row_padding = 11 * SCALE
    wrapped_rows: list[list[list[str]]] = []
    row_heights: list[int] = []
    for row in rows:
        wrapped = [
            wrap(value, cell_font, (column_width - 22) * SCALE)
            for value, column_width in zip(row, widths)
        ]
        wrapped_rows.append(wrapped)
        line_count = max(len(cell) for cell in wrapped)
        row_heights.append(max(45 * SCALE, line_count * line_height + row_padding * 2))

    height = 2 * SCALE + header_height + sum(row_heights) + 2 * SCALE
    image = Image.new("RGB", (WIDTH * SCALE, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (1 * SCALE, 1 * SCALE, (WIDTH - 2) * SCALE, height - 1),
        radius=12 * SCALE,
        fill=PANEL,
        outline=BORDER,
        width=1 * SCALE,
    )
    x0 = pad * SCALE
    y = 2 * SCALE
    draw.rectangle((x0, y, (WIDTH - pad) * SCALE, y + header_height), fill=(36, 48, 63))
    x = x0
    for label, width in zip(headers, widths):
        draw.text(
            (x + 11 * SCALE, y + header_height // 2),
            label,
            font=header_font,
            fill=GREEN,
            anchor="lm",
        )
        x += width * SCALE
    y += header_height

    for row_index, (wrapped, row_height) in enumerate(zip(wrapped_rows, row_heights)):
        fill = PANEL_ALT if row_index % 2 else PANEL
        draw.rectangle((x0, y, (WIDTH - pad) * SCALE, y + row_height), fill=fill)
        x = x0
        for column_index, (lines, width) in enumerate(zip(wrapped, widths)):
            color = TEXT if column_index == 0 else MUTED
            for line_index, line in enumerate(lines):
                draw.text(
                    (x + 11 * SCALE, y + row_padding + line_index * line_height),
                    line,
                    font=cell_font,
                    fill=color,
                    anchor="la",
                )
            x += width * SCALE
        y += row_height
        draw.line((x0, y, (WIDTH - pad) * SCALE, y), fill=BORDER, width=1 * SCALE)
    save(image, name)


def forms_cards(name: str, locale: str) -> None:
    is_ru = locale == "ru"
    title_font = font(15, True)
    body_font = font(11.5)
    cards = (
        [
            (
                "Точно",
                "Только написанная форма. «открыл зонт» не совпадёт с «открывает зонт». Для имён и точных фраз.",
            ),
            (
                "Основы",
                "Сравнение по основе: «открыл / открывает / откроет» → «откр». Без словаря, работает всегда.",
            ),
            (
                "Леммы",
                "Основа + словарная форма pymorphy3: «зонта / зонт», «люди / человек». Без пакета — как «Основы».",
            ),
        ]
        if is_ru
        else [
            (
                "Exact",
                "Only the written form. «открыл зонт» will not match «открывает зонт». Useful for names and exact phrases.",
            ),
            (
                "Stems",
                "Compares word stems: «открыл / открывает / откроет» → «откр». No dictionary required.",
            ),
            (
                "Lemmas",
                "Stem + pymorphy3 dictionary forms: «зонта / зонт», «люди / человек». Without the package, falls back to Stems.",
            ),
        ]
    )
    image = Image.new("RGB", (WIDTH * SCALE, 278 * SCALE), BG)
    draw = ImageDraw.Draw(image)
    title = (
        "Выберите, насколько широко искать словоформы"
        if is_ru
        else "Choose how broadly to match word forms"
    )
    draw.text((18 * SCALE, 24 * SCALE), title, font=font(14, True), fill=MUTED, anchor="lm")
    gap = 12
    card_width = (WIDTH - 32 - gap * 2) // 3
    card_top, card_bottom = 48, 267
    accent_colors = [BLUE, GREEN, (183, 150, 245)]
    for index, (label, description) in enumerate(cards):
        left = 16 + index * (card_width + gap)
        right = left + card_width
        draw.rounded_rectangle(
            (left * SCALE, card_top * SCALE, right * SCALE, card_bottom * SCALE),
            radius=10 * SCALE,
            fill=PANEL if index != 1 else PANEL_ALT,
            outline=BORDER,
            width=1 * SCALE,
        )
        draw.rounded_rectangle(
            (
                (left + 13) * SCALE,
                (card_top + 16) * SCALE,
                (left + 17) * SCALE,
                (card_top + 43) * SCALE,
            ),
            radius=2 * SCALE,
            fill=accent_colors[index],
        )
        draw.text(
            ((left + 28) * SCALE, (card_top + 30) * SCALE),
            label,
            font=title_font,
            fill=TEXT,
            anchor="lm",
        )
        lines = wrap(description, body_font, (card_width - 28) * SCALE)
        y = (card_top + 66) * SCALE
        line_height = 18 * SCALE
        for line in lines:
            draw.text(((left + 14) * SCALE, y), line, font=body_font, fill=MUTED, anchor="la")
            y += line_height
    save(image, name)


def generate(locale: str) -> None:
    is_ru = locale == "ru"
    labels = (
        [
            "О проекте",
            "Возможности",
            "Как устроен перевод",
            "Языки и словари",
            "Модули и настройки",
            "Анимации: правила и словоформы",
            "Скачать и установить",
            "Проверка безопасности",
            "DeepLX в России",
            "Лицензия и контакты",
        ]
        if is_ru
        else [
            "About the project",
            "Features",
            "Translation workflow",
            "Languages and glossaries",
            "Modules and settings",
            "Animations: rules and word forms",
            "Download and installation",
            "Security report",
            "DeepLX in Russia",
            "License and contacts",
        ]
    )
    hero("sm_header.png" if is_ru else "sm_header_en.png", locale)
    whats_new_header(f"post_whats_new_{locale}.png", locale)
    for number, label in enumerate(labels, start=1):
        section(f"post_section_{number:02d}_{locale}.png", label, number)
    forms_cards(f"post_animation_forms_{locale}.png", locale)

    module_rows = (
        [
            ["Перевод по сети", "Google, MyMemory, Lingva, LibreTranslate", "Вкл."],
            ["Словарь", "Готовые RP-фразы и русская запись", "Вкл."],
            ["Сленг", "Раскрытие сокращений до перевода", "Вкл."],
            ["Автоперевод", "Перевод каждого N-го сообщения", "Выкл."],
            ["Отправка в игру", "Вставка текста в игровой чат", "Вкл."],
            ["DeepL рядом (DLX)", "Локальный сервис DeepL", "Выкл."],
            ["Анимации", "Запуск по ключевым словам", "Выкл."],
            ["Глобальная клавиша", "Вызов оверлея одной клавишей", "Вкл."],
        ]
        if is_ru
        else [
            ["Online translation", "Google, MyMemory, Lingva, LibreTranslate", "On"],
            ["Glossary", "Ready-made RP phrases and Russian reading", "On"],
            ["Slang", "Expand abbreviations before translation", "On"],
            ["Auto-translation", "Translate every N-th message", "Off"],
            ["Send to game", "Insert text into the in-game chat", "On"],
            ["DeepL alongside (DLX)", "Local DeepL service", "Off"],
            ["Animations", "Keyword-triggered actions", "Off"],
            ["Global hotkey", "Open the overlay with one key", "On"],
        ]
    )
    module_headers = (
        ["Модуль", "Назначение", "По умолчанию"] if is_ru else ["Module", "Purpose", "Default"]
    )
    table(
        f"post_modules_{locale}.png",
        module_headers,
        module_rows,
        [165, 435, 88],
    )

    language_rows = (
        [
            ["Итальянский", "it", "Встроенный словарь"],
            ["Испанский", "es", "Встроенный словарь"],
            ["Испанский (Мексика)", "es-MX", "Встроенный словарь"],
            ["Португальский (Бразилия)", "pt-BR", "Встроенный словарь"],
            ["Китайский", "zh-CN", "Встроенный словарь"],
            ["Японский", "ja", "Встроенный словарь"],
            ["Английский", "en", "Встроенный словарь"],
            ["Немецкий", "de", "Встроенный словарь"],
            ["Французский", "fr", "Встроенный словарь"],
            ["Польский", "pl", "Встроенный словарь"],
            ["Турецкий", "tr", "Встроенный словарь"],
            ["Корейский", "ko", "Онлайн-перевод; словарь можно добавить"],
            ["Арабский", "ar", "Онлайн-перевод; словарь можно добавить"],
        ]
        if is_ru
        else [
            ["Italian", "it", "Built-in glossary"],
            ["Spanish", "es", "Built-in glossary"],
            ["Spanish (Mexico)", "es-MX", "Built-in glossary"],
            ["Portuguese (Brazil)", "pt-BR", "Built-in glossary"],
            ["Chinese", "zh-CN", "Built-in glossary"],
            ["Japanese", "ja", "Built-in glossary"],
            ["English", "en", "Built-in glossary"],
            ["German", "de", "Built-in glossary"],
            ["French", "fr", "Built-in glossary"],
            ["Polish", "pl", "Built-in glossary"],
            ["Turkish", "tr", "Built-in glossary"],
            ["Korean", "ko", "Online; custom glossary supported"],
            ["Arabic", "ar", "Online; custom glossary supported"],
        ]
    )
    language_headers = ["Язык", "Код", "Словарь"] if is_ru else ["Language", "Code", "Glossary"]
    table(
        f"post_languages_{locale}.png",
        language_headers,
        language_rows,
        [250, 92, 346],
    )


if __name__ == "__main__":
    generate("ru")
    generate("en")
