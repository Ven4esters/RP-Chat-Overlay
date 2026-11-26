"""Язык интерфейса программы (русский / английский) / interface language.

Английский каталог интерфейса вынесен в app.i18n_en; ключ — ровно та русская
строка, которая стоит в коде. The English catalog lives in app.i18n_en, keyed
by the exact Russian string that appears in the code.

Как устроено
------------
В коде интерфейс написан по-русски, а английский вариант лежит в таблице
STRINGS: ключ — ровно та строка, которая стоит в коде. Функция t() возвращает
перевод для текущего языка интерфейса, а retranslate() проходит по дереву
виджетов и подменяет подписи, подсказки, заголовки колонок и элементы списков.

Исходный русский текст каждой подписи запоминается в свойстве виджета, поэтому
переключение языка работает в любую сторону и любое число раз, без перезапуска
и без потери строк.

Для чисел заведены шаблоны: t("всего фраз: %d") % n — формат подставляется
уже после перевода.
"""

from app.i18n_en import STRINGS

RU = "ru"
EN = "en"

_current = RU


def normalize(code):
    """'en', 'en-US', 'English' -> 'en'; всё остальное — 'ru'."""
    return EN if str(code or "").strip().lower().startswith("en") else RU


def set_lang(code):
    """Задать язык интерфейса и вернуть его код.

    Set the interface language and return its code.
    """
    global _current
    _current = normalize(code)
    return _current


def lang():
    return _current


def is_en():
    return _current == EN


def t(text):
    """Перевод строки интерфейса на текущий язык (по умолчанию — как есть).

    Translate an interface string into the current language (as is by default).
    """
    if _current == RU:
        return text
    return STRINGS.get(text, text)


def tf(text, *args):
    """Перевод шаблона с подстановкой: tf("всего фраз: %d", 12).

    Translate a template and substitute: tf("всего фраз: %d", 12).
    """
    out = t(text)
    try:
        return out % args if args else out
    except (TypeError, ValueError):
        return out


def _remember(obj, attr, value):
    """Запоминает исходный русский текст в свойстве виджета.

    Remembers the original Russian text in a widget property.
    """
    key = "_ru_" + attr
    stored = obj.property(key)
    if stored is None:
        obj.setProperty(key, value)
        return value
    return stored


def _set_text(obj, attr, setter, value):
    """Ставит перевод, помня исходную строку.

    Sets the translation while remembering the original string.
    """
    original = _remember(obj, attr, value)
    new = t(original)
    if setter is not None:
        setter(new)


def retranslate(root):
    """Проходит по дереву виджетов и переводит все подписи на текущий язык.

    Walks the widget tree and translates every caption into the current language.
    """
    try:
        from PySide6.QtWidgets import (
            QAbstractSpinBox,
            QCheckBox,
            QComboBox,
            QGroupBox,
            QLabel,
            QLineEdit,
            QListWidget,
            QPlainTextEdit,
            QPushButton,
            QRadioButton,
            QTableWidget,
            QTabBar,
            QTextEdit,
            QWidget,
        )
    except Exception:  # без Qt функция просто молчит
        return root
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        try:
            if w.property("no_i18n"):  # подпись собирается в коде — не трогаем
                continue
            if isinstance(w, (QLabel, QPushButton, QCheckBox, QRadioButton)):
                _set_text(w, "text", w.setText, w.text())
            elif isinstance(w, QGroupBox):
                _set_text(w, "title", w.setTitle, w.title())
            elif isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
                _set_text(w, "ph", w.setPlaceholderText, w.placeholderText())
            elif isinstance(w, QAbstractSpinBox):
                _set_text(w, "suffix", w.setSuffix, w.suffix())
            if isinstance(w, QComboBox):
                items = w.property("_ru_items")
                if items is None:
                    items = [w.itemText(i) for i in range(w.count())]
                    w.setProperty("_ru_items", items)
                for i, s in enumerate(items):
                    w.setItemText(i, t(s))
            elif isinstance(w, QListWidget):
                items = w.property("_ru_items")
                if items is None:
                    items = [w.item(i).text() for i in range(w.count())]
                    w.setProperty("_ru_items", items)
                for i, s in enumerate(items):
                    w.item(i).setText(t(s))
            elif isinstance(w, QTableWidget):
                head = w.horizontalHeader()
                items = head.property("_ru_items")
                if items is None:
                    items = [
                        w.horizontalHeaderItem(i).text() if w.horizontalHeaderItem(i) else ""
                        for i in range(w.columnCount())
                    ]
                    head.setProperty("_ru_items", items)
                for i, s in enumerate(items):
                    item = w.horizontalHeaderItem(i)
                    if item is not None:
                        item.setText(t(s))
            elif isinstance(w, QTabBar):
                for i in range(w.count()):
                    w.setTabText(i, t(w.tabText(i)))
            tip = w.property("_ru_tip")
            if tip is None and w.toolTip():
                w.setProperty("_ru_tip", w.toolTip())
                tip = w.toolTip()
            if tip:
                w.setToolTip(t(tip))
            title = w.property("_ru_title")
            if title is None and w.windowTitle():
                w.setProperty("_ru_title", w.windowTitle())
                title = w.windowTitle()
            if title:
                w.setWindowTitle(t(title))
        except Exception:  # один сбойный виджет не ломает окно
            continue
    return root


# ---------------------------------------------------------------- словарь
#
# Ключ — русская строка из кода, значение — английский вариант.
# Шаблоны с %d/%s переводятся целиком, подстановка идёт после перевода.
# the dictionary
#
# the key is the Russian string from the code, the value is the English one.
# %d/%s templates are translated whole, the substitution happens afterwards.
