#!/usr/bin/env python3
"""Отрисованные подзаголовки и разделитель для темы на форуме.

Форум плохо переносит вложенную разметку, поэтому заголовки разделов
рисуем картинками в том же стиле, что и таблицы: панель, скругление,
акцентная полоса слева. Уровень 1 — крупный заголовок раздела,
уровень 2 — подраздел, «версия» — заголовок выпуска.

Запускать из каталога source/images/forum.
"""

import pathlib

import make_forum_reverse as base

OUT = pathlib.Path(__file__).parent
PANEL, BORDER = "#191d26", "#2b3140"
TXT = "#f2f4f8"
ACCENT_BAR = "url(#bar)"  # синий → зелёный, как на кнопках
W = 720


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def head(name, text, level=2):
    """level: 1 — раздел, 2 — подраздел, 3 — версия."""
    fs = {1: 25.0, 2: 17.0, 3: 23.0}[level]
    h = {1: 66, 2: 48, 3: 60}[level]
    bar_w = {1: 6, 2: 4, 3: 6}[level]
    bar_h = {1: 30, 2: 20, 3: 26}[level]
    fill = PANEL if level != 2 else "#1c212c"
    fs = base.fit(text, W - 2 * 14 - bar_w - 13 - 10, fs, bold=True)

    by = (h - bar_h) / 2
    bar_x = 14
    parts = [
        f'<rect width="{W}" height="{h}" rx="12" fill="{fill}" stroke="{BORDER}"/>',
        f'<rect x="{bar_x}" y="{by}" width="{bar_w}" height="{bar_h}" '
        f'rx="{bar_w / 2}" fill="{ACCENT_BAR}"/>',
        f'<text x="{bar_x + bar_w + 13}" y="{h / 2 + fs * 0.35:.1f}" font-size="{fs}" '
        f'font-weight="bold" fill="{TXT}">{esc(text)}</text>',
    ]
    base.render(name, base.svg(W, h, "".join(parts)))


def divider(name="div_line"):
    """Тонкая линия, растворяющаяся по краям: разделяет подпункты."""
    w, h = W, 18
    body = (
        '<defs><linearGradient id="ln" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#2b3140" stop-opacity="0"/>'
        '<stop offset="0.18" stop-color="#2b3140" stop-opacity="0.95"/>'
        '<stop offset="0.82" stop-color="#2b3140" stop-opacity="0.95"/>'
        '<stop offset="1" stop-color="#2b3140" stop-opacity="0"/>'
        "</linearGradient></defs>"
        f'<rect x="0" y="{h / 2 - 0.5}" width="{w}" height="1" fill="url(#ln)"/>'
        f'<rect x="{w / 2 - 2.5}" y="{h / 2 - 2.5}" width="5" height="5" rx="2.5" '
        f'fill="#57c98a" fill-opacity="0.5"/>'
    )
    base.render(name, base.svg(w, h, body))


# ------------------------------------------------------------------ заголовки
MAJOR = [
    ("hdr_whats_new", "Что нового"),
    ("hdr_download", "Скачать"),
    ("hdr_english", "English"),
]

SECTIONS = [
    ("hdr_how", "Как это работает"),
    ("hdr_features", "Что умеет программа"),
    ("hdr_directions", "Два направления перевода"),
    ("hdr_dict", "Словарь и сокращения"),
    ("hdr_langs", "Языки перевода"),
    ("hdr_settings", "Окно настроек"),
    ("hdr_history", "История версий"),
    ("hdr_services", "Перевод и сервисы"),
    ("hdr_abbr", "Сокращения"),
    ("hdr_docs", "Документация"),
]

VERSIONS = [
    ("hdr_v15", "Версия 1.5"),
    ("hdr_v13", "Версия 1.3"),
    ("hdr_v12", "Версия 1.2"),
    ("hdr_v11", "Версия 1.1"),
    ("hdr_v10", "Версия 1.0"),
]

if __name__ == "__main__":
    print("подзаголовки:")
    for n, t in MAJOR:
        head(n, t, 1)
    for n, t in VERSIONS:
        head(n, t, 3)
    for n, t in SECTIONS:
        head(n, t, 2)
    divider()
