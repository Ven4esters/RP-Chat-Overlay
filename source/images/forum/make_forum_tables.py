#!/usr/bin/env python3
"""Отрисованные таблицы для темы на форуме.

Форум не поддерживает [table], поэтому таблицы отдаём картинками: тёмная
панель, шапка с подложкой, чередование строк, щедрые отступы — читается
и на светлой, и на тёмной теме оформления.

Ширина 720 px: форум вставляет картинку в натуральную величину, при этом
на узких экранах она ужимается без потери смысла (крупный кегль, мало колонок).
"""
import pathlib

import make_forum_reverse as base

OUT = pathlib.Path(__file__).parent
PANEL, BORDER = "#191d26", "#2b3140"
TXT, DIM, MUT = "#f2f4f8", "#c3cadd", "#8b95a9"
HEAD_BG = "#232a3a"
ROW_A, ROW_B = "#1b1f29", "#20242f"
ACCENT = "#57c98a"
BLUE = "#5b8bf0"

_measure = base.measure
_font_path = base._F
# для китайского, японского и корейского нужен запасной шрифт: DejaVu их не знает
FONT = "DejaVu Sans, Noto Sans CJK SC, Noto Sans CJK JP, sans-serif"
base.FONT = FONT


def wrap(text, max_w, size, bold=False):
    """Разбивает текст по словам под ширину колонки."""
    out, cur = [], ""
    for word in str(text).split():
        probe = (cur + " " + word).strip()
        if _measure(probe, size, bold) <= max_w or not cur:
            cur = probe
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out or [""]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def table(name, headers, rows, cols, width=720, fs=13.0, title=None,
          note=None, first_col_bold=True):
    """Рисует таблицу в PNG и заодно сохраняет SVG (исходник правок)."""
    assert abs(sum(cols) + 2 * 16 - width) < 60, (sum(cols), width)
    pad = 16                 # внешние поля панели
    cpad = 13                # поля внутри ячейки
    lh = fs * 1.42           # высота строки текста
    row_pad = 9
    head_fs = fs - 0.5
    head_h = head_fs * 2.4

    # --- разбивка по строкам и высоты строк
    heights, wrapped = [], []
    for row in rows:
        cells, lines_max = [], 1
        for txt, w in zip(row, cols):
            lines = wrap(txt, w - 2 * cpad, fs, first_col_bold and txt is row[0])
            cells.append(lines)
            lines_max = max(lines_max, len(lines))
        wrapped.append(cells)
        heights.append(lines_max * lh + 2 * row_pad)

    title_h = 0
    if title:
        title_h = fs * 2.6
    note_lines = wrap(note, width - 2 * pad, fs - 2) if note else []
    note_h = (len(note_lines) * (fs - 2) * 1.5 + 8) if note else 0

    body_h = head_h + sum(heights)
    h = int(pad + title_h + body_h + note_h + pad)

    x0 = pad
    inner_w = width - 2 * pad

    parts = [
        f'<rect width="{width}" height="{h}" rx="14" fill="{PANEL}" stroke="{BORDER}"/>'
    ]

    y = pad
    if title:
        parts.append(
            f'<text x="{x0}" y="{y + fs * 1.35:.1f}" font-size="{fs + 2.5}" '
            f'font-weight="bold" fill="{TXT}">{esc(title)}</text>')
        y += title_h

    # шапка
    parts.append(f'<path d="M{x0} {y} h{inner_w} v{head_h} h-{inner_w} z" fill="{HEAD_BG}"/>')
    cx = x0
    for head, w in zip(headers, cols):
        parts.append(
            f'<text x="{cx + cpad}" y="{y + head_h / 2 + head_fs * 0.36:.1f}" '
            f'font-size="{head_fs}" font-weight="bold" fill="{DIM}">{esc(head)}</text>')
        cx += w
    parts.append(f'<line x1="{x0}" y1="{y + head_h}" x2="{x0 + inner_w}" '
                 f'y2="{y + head_h}" stroke="{BORDER}" stroke-width="1"/>')
    y += head_h

    # строки
    for i, (cells, rh) in enumerate(zip(wrapped, heights)):
        fill = ROW_A if i % 2 == 0 else ROW_B
        parts.append(f'<rect x="{x0}" y="{y:.1f}" width="{inner_w}" height="{rh:.1f}" fill="{fill}"/>')
        cx = x0
        for j, (lines, w) in enumerate(zip(cells, cols)):
            bold = first_col_bold and j == 0
            color = TXT if j == 0 else DIM
            ty = y + row_pad + fs
            weight = ' font-weight="bold"' if bold else ""
            for line in lines:
                parts.append(
                    f'<text x="{cx + cpad}" y="{ty:.1f}" font-size="{fs}"'
                    f'{weight} fill="{color}">{esc(line)}</text>')
                ty += lh
            cx += w
        y += rh
        if i < len(wrapped) - 1:
            parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + inner_w}" '
                         f'y2="{y:.1f}" stroke="{PANEL}" stroke-width="1"/>')

    # нижнее скругление — перекрываем углы панелью-рамкой
    parts.append(f'<rect x="{x0 - 1}" y="{y - 1}" width="{inner_w + 2}" height="2" '
                 f'fill="{PANEL}"/>')

    if note:
        ty = y + 6 + (fs - 2)
        for line in note_lines:
            parts.append(f'<text x="{x0 + 2}" y="{ty:.1f}" font-size="{fs - 2}" '
                         f'fill="{MUT}">{esc(line)}</text>')
            ty += (fs - 2) * 1.5

    svg_doc = base.svg(width, h, "".join(parts))
    base.render(name, svg_doc)


# ------------------------------------------------------------------ таблицы
def features():
    table(
        "tbl_features",
        ["Возможность", "Что происходит"],
        [
            ("Перевод из русского", "Печатаете по-русски — в чат игры уходит фраза на выбранном языке. "
                                    "Русская запись остаётся под рукой: её видно в оверлее до отправки."),
            ("Режим для иностранного игрока", "Пишете на своём языке — в чат уходит русский перевод целиком, "
                                              "вместе с действиями *…*. Служебные команды и ники не переводятся."),
            ("13 языков перевода", "От итальянского и испанского до китайского, японского и арабского. "
                                   "У одиннадцати языков есть встроенный словарь и слова-паразиты."),
            ("Словарь", "Готовые фразы с русской записью («как это читается вслух») и значениями. "
                        "Свои фразы добавляются в окне настроек, импорт из JSON и CSV."),
            ("Сленг и сокращения", "180 сокращений и растянутый смех: brb, afk, gg, tysm, afaik, wtb. "
                                   "Сокращение раскрывается до перевода, поэтому падеж и род получаются верными."),
            ("Автоперевод по счётчику", "Переводится каждое N-е сообщение или только помеченное +маркерами+. "
                                        "Команды /to, /lto, /l, /wt, /s, /st считаются наравне с обычными."),
            ("Слова-паразиты", "Senti, Ma dai, Oye, китайские частицы — подставляются в каждом сообщении, "
                               "независимо от счётчика. Список свой для каждого языка."),
            ("Отправка в игру", "Оверлей сам открывает чат клавишей T, вставляет текст и отправляет по Enter. "
                                "Три задержки настраиваются, если сервер медленный."),
            ("Два языка интерфейса", "Первый запуск спрашивает: русский или English. "
                                     "Переключение — в настройках, сразу и без перезапуска."),
        ],
        cols=[212, 460], fs=13.0,
        note="Всё перечисленное настраивается в окне программы и работает на чистой Windows "
             "без установки Python.")


def languages():
    table(
        "tbl_langs",
        ["Язык", "Код", "Словарь и слова-паразиты"],
        [
            ("Итальянский — Italiano", "it", "103 фразы · 10 паразитов"),
            ("Испанский — Español", "es", "46 фраз · 7 паразитов"),
            ("Мексиканский — Español (MX)", "es-MX", "51 фраза · 8 паразитов"),
            ("Португальский — Português (BR)", "pt-BR", "49 фраз · 8 паразитов"),
            ("Английский — English", "en", "37 фраз · 8 паразитов"),
            ("Немецкий — Deutsch", "de", "32 фразы · 8 паразитов"),
            ("Французский — Français", "fr", "33 фразы · 9 паразитов"),
            ("Польский — Polski", "pl", "36 фраз · 8 паразитов"),
            ("Турецкий — Türkçe", "tr", "41 фраза · 9 паразитов"),
            ("Китайский — Zhōngwén", "zh-CN", "46 фраз · 8 паразитов"),
            ("Японский — Nihongo", "ja", "40 фраз · 8 паразитов"),
            ("Корейский — Hangugeo", "ko", "перевод по сети"),
            ("Арабский — Al-arabiyya", "ar", "перевод по сети"),
        ],
        cols=[300, 84, 288], fs=13.0,
        note="Словарь подсказывает, как фразу читать вслух, и работает без интернета. "
             "Для языков без словаря текст переводится сервисами в сети.")


def settings():
    table(
        "tbl_settings",
        ["Раздел", "Что настраивается"],
        [
            ("Основные", "Язык перевода · что уходит в чат · язык интерфейса · горячая клавиша · "
                         "масштаб окна · скобки перевода · лимит символов · раскрытие сокращений."),
            ("Автоперевод", "Частота «каждое N-е» · какое сообщение в серии · длина и число фрагментов · "
                            "приоритет словаря · слова-паразиты «всегда» и их список."),
            ("Чат игры", "Вставлять в чат · сначала открывать чат клавишей T · отправлять по Enter · "
                         "клавиша чата · три задержки для медленных серверов."),
            ("Словарь", "Таблица фраз с поиском, добавление и удаление, импорт JSON и CSV, экспорт, "
                        "возврат встроенного словаря."),
            ("Сокращения", "Свои сокращения по образцу словаря: сокращение, разворот и короткий русский "
                           "вариант. Своя строка перекрывает встроенную, пустые колонки выключают."),
            ("Проверка", "Живой предпросмотр в обе стороны: видно, что именно уйдёт в чат игры, "
                         "и как это читается вслух."),
        ],
        cols=[150, 522], fs=13.0,
        note="Подсказка есть у каждого поля. Окно подстраивается под экран, разделы прокручиваются, "
             "масштаб интерфейса меняется от 80 до 180 %.")


def versions():
    table(
        "tbl_versions",
        ["Версия", "Главное"],
        [
            ("1.5", "Адаптивное окно и масштаб интерфейса · цепочка сервисов перевода с подменой "
                    "при ответе 429 · 180 сокращений · README на двух языках · CHANGELOG."),
            ("1.4", "Английский интерфейс с выбором языка при первом запуске · свои сокращения · "
                    "проверка перевода в обе стороны."),
            ("1.3", "Сленг и сокращения раскрываются до перевода: brb → «я скоро вернусь»."),
            ("1.2", "Короткое меню в трее из четырёх строк: статус, направление, настройки, выход."),
            ("1.1", "Режим для иностранного игрока: любой язык → русский, перевод уходит в чат."),
            ("1.0", "Первый выпуск: оверлей, 13 языков, словарь, автоперевод, отправка в игру."),
        ],
        cols=[80, 592], fs=13.0,
        note="Подробности по каждой версии — в CHANGELOG.md в репозитории.")


if __name__ == "__main__":
    print("рендер таблиц:")
    features()
    languages()
    settings()
    versions()
