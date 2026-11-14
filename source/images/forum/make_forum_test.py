#!/usr/bin/env python3
"""Картинка для темы: окно «Проверка перевода» в направлении «Ваш язык → русский» (1.4.1).

Ширина 480 px — форум вставляет [img] в натуральную величину.
Использует те же шрифты и цвета, что и остальная графика темы.
"""
import pathlib

import make_forum_reverse as base  # noqa: E402  (общие DEFS/метрики/рендер)

OUT = pathlib.Path(__file__).parent
PANEL, BORDER = base.PANEL, base.BORDER
TXT, DIM, MUT = base.TXT, base.DIM, base.MUT
GREEN = base.GREEN
fit, measure, svg, render = base.fit, base.measure, base.svg, base.render

W, H = 480, 224
F_SANS = base._F[False]
F_BOLD = base._F[True]


def wrap(text, max_w, size, bold=False):
    """Разбивает строку по словам так, чтобы каждая влезала в max_w."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if measure(probe, size, bold) <= max_w or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def card():
    b = [f'<rect width="{W}" height="{H}" rx="12" fill="{PANEL}" stroke="{BORDER}"/>']

    y = 26
    b.append(f'<text x="16" y="{y}" font-size="14" font-weight="bold" fill="{TXT}">'
             f'Проверка перевода</text>')

    # подсказка под заголовком
    y += 18
    hint = ("Введите фразу на языке сервера — увидите, что именно уйдёт в чат игры "
            "на русском.")
    for line in wrap(hint, W - 32, 10.5):
        b.append(f'<text x="16" y="{y}" font-size="10.5" fill="{MUT}">{line}</text>')
        y += 14

    # направление
    y += 6
    b.append(f'<text x="16" y="{y + 18}" font-size="11" fill="{DIM}">Направление:</text>')
    bw = 244
    bx = W - 16 - bw
    b.append(f'<rect x="{bx}" y="{y}" width="{bw}" height="26" rx="6" '
             f'fill="#11141c" stroke="{BORDER}"/>')
    b.append(f'<text x="{bx + 10}" y="{y + 17.5}" font-size="11.5" fill="{TXT}">'
             f'Ваш язык → русский</text>')
    b.append(f'<path d="M{bx + bw - 18} {y + 11}l4 5 4-5" fill="none" stroke="{MUT}" '
             f'stroke-width="1.4"/>')

    # поле ввода
    y += 34
    b.append(f'<rect x="16" y="{y}" width="{W - 32}" height="28" rx="6" '
             f'fill="#11141c" stroke="{base.BLUE}"/>')
    b.append(f'<text x="26" y="{y + 18.5}" font-size="11.5" fill="{TXT}">'
             f'What y can r do? Afk man</text>')

    # карточка результата
    y += 36
    res = "я скоро вернусь, я не за клавиатурой"
    sub = "Способ: переведено в чат игры"
    b.append(f'<rect x="16" y="{y}" width="{W - 32}" height="64" rx="8" '
             f'fill="#141822" stroke="{BORDER}"/>')
    b.append(f'<text x="28" y="{y + 22}" font-size="{fit(res, W - 56, 13)}" '
             f'fill="{TXT}">{res}</text>')
    b.append(f'<text x="28" y="{y + 39}" font-size="10" fill="{MUT}">'
             f'Исходное сообщение: I\'m not at the keyboard man</text>')
    b.append(f'<text x="28" y="{y + 55}" font-size="10" fill="{GREEN}">{sub}</text>')
    return svg(W, H, "".join(b))


if __name__ == "__main__":
    print("рендер (проверка в режиме «ваш язык → русский»):")
    render("ui_test", card())
