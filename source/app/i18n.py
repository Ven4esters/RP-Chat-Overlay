"""Язык интерфейса программы (русский / английский) / interface language.

Английский вариант интерфейса лежит в таблице STRINGS: ключ — ровно та русская
строка, которая стоит в коде. The English UI lives in the STRINGS table, keyed
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
RU = "ru"
EN = "en"

_current = RU


def normalize(code):
    """'en', 'en-US', 'English' -> 'en'; всё остальное — 'ru'."""
    return EN if str(code or "").strip().lower().startswith("en") else RU


def set_lang(code):
    """Задать язык интерфейса и вернуть его код."""
    global _current
    _current = normalize(code)
    return _current


def lang():
    return _current


def is_en():
    return _current == EN


def t(text):
    """Перевод строки интерфейса на текущий язык (по умолчанию — как есть)."""
    if _current == RU:
        return text
    return STRINGS.get(text, text)


def tf(text, *args):
    """Перевод шаблона с подстановкой: tf("всего фраз: %d", 12)."""
    out = t(text)
    try:
        return out % args if args else out
    except (TypeError, ValueError):
        return out


def lang_name(code):
    """Название языка интерфейса для списка в настройках."""
    return {"ru": "Русский", "en": "English"}[normalize(code)]


def _remember(obj, attr, value):
    """Запоминает исходный русский текст в свойстве виджета."""
    key = "_ru_" + attr
    stored = obj.property(key)
    if stored is None:
        obj.setProperty(key, value)
        return value
    return stored


def _set_text(obj, attr, setter, value):
    """Ставит перевод, помня исходную строку."""
    original = _remember(obj, attr, value)
    new = t(original)
    if setter is not None:
        setter(new)


def retranslate(root):
    """Проходит по дереву виджетов и переводит все подписи на текущий язык."""
    try:
        from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox,
                                       QGroupBox, QLabel, QLineEdit, QListWidget,
                                       QPlainTextEdit, QPushButton, QRadioButton,
                                       QTableWidget, QTabBar, QTextEdit, QWidget)
    except Exception:                                    # без Qt функция просто молчит
        return root
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        try:
            if w.property("no_i18n"):        # подпись собирается в коде — не трогаем
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
                    items = [w.horizontalHeaderItem(i).text()
                             if w.horizontalHeaderItem(i) else ""
                             for i in range(w.columnCount())]
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
        except Exception:                                  # один сбойный виджет не ломает окно
            continue
    return root


# ---------------------------------------------------------------- словарь
#
# Ключ — русская строка из кода, значение — английский вариант.
# Шаблоны с %d/%s переводятся целиком, подстановка идёт после перевода.
STRINGS = {
    # ---------- окно настроек: каркас ----------
    "Настройки — RP Chat Overlay": "Settings — RP Chat Overlay",
    "Настройки": "Settings",
    "Основные": "General",
    "Автоперевод": "Auto-translation",
    "Чат игры": "Game chat",
    "Словарь": "Glossary",
    "Сокращения": "Abbreviations",
    "Проверка": "Test",
    "Сохранить": "Save",
    "Отмена": "Cancel",
    "Сбросить всё": "Reset all",
    "Вернуть заводские настройки (словари не затрагиваются)":
        "Restore factory settings (glossaries are kept)",
    "Изменения применятся после «Сохранить».": "Changes apply after you press Save.",
    "Настройки сброшены — нажмите «Сохранить», чтобы применить.":
        "Settings reset — press Save to apply.",
    "Добро пожаловать в RP Chat Overlay": "Welcome to RP Chat Overlay",
    "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е":
        "Language: %s · hotkey: %s · auto-translation: every %d-th message",

    # ---------- Основные: язык перевода ----------
    "Язык перевода": "Target language",
    "Печатаете по-русски — в чат игры уходит текст на выбранном языке.":
        "You type in Russian — the chosen language goes to the game chat.",
    "Что уходит в чат:": "What goes to the chat:",
    "Русская запись — как это читается": "Russian reading — how it sounds",
    "Текст на языке — для международных серверов":
        "Text in the language — for international servers",
    "«Русская запись» — в чат уходит «Чао» (кириллицей), как в исходной версии.\n"
    "«Текст на языке» — в чат уходит «Ciao» (для серверов, где читают латиницу).":
        "«Russian reading» — the chat gets «Чао» in Cyrillic, as in the first version.\n"
        "«Text in the language» — the chat gets «Ciao» (for servers that read Latin).",
    "Язык, на который переводится ваш текст":
        "The language your text is translated into",
    "Язык интерфейса": "Interface language",
    "Язык кнопок, подсказок и меню. Применяется сразу.":
        "The language of buttons, hints and menus. Applied immediately.",

    # ---------- Основные: режим переводчика ----------
    "Перевод входящего текста": "Incoming text translation",
    "Режим для иностранного игрока на русскоязычном сервере: пишете в оверлее "
    "на своём языке — в чат уходит перевод на русский. Переводится каждое "
    "сообщение целиком, включая действия *...*; служебные команды (/me, /to "
    "и другие) остаются без перевода.":
        "A mode for a foreign player on a Russian-speaking server: you type in "
        "the overlay in your own language and the Russian translation goes to the "
        "chat. Every message is translated as a whole, actions *...* included; "
        "service commands (/me, /to and others) are left as they are.",
    "Переводить на русский (режим переводчика)":
        "Translate to Russian (interpreter mode)",
    "Ваш язык → русский. Enter отправляет перевод в чат игры.\n"
    "Служебные команды через / не переводятся.":
        "Any language → Russian. Enter sends the translation to the game chat.\n"
        "Service commands starting with / are not translated.",
    "Включено: пишете на своём языке — Enter отправляет перевод на русский в чат "
    "игры. Команды /… не переводятся.":
        "On: you type in your own language — Enter sends the Russian translation to "
        "the game chat. Commands /… are not translated.",
    "Выключено: обычный режим — русский текст переводится на выбранный язык "
    "перевода.":
        "Off: the usual mode — Russian text is translated into the server language.",

    # ---------- Основные: сленг ----------
    "Сленг и сокращения": "Slang and abbreviations",
    "Сокращения из живого чата раскрываются до перевода, поэтому в русском "
    "тексте сразу верные падеж, род и время: «brb» → «я скоро вернусь», «afk» → "
    "«я не за клавиатурой», «ty» → «спасибо». Если сервис всё же вернёт «afk» "
    "или «gg» латиницей, подставляется короткий русский вариант. В обратную "
    "сторону так же раскрываются русские сокращения: «спс» → «спасибо», «мб» → "
    "«может быть».":
        "Abbreviations from live chat are expanded before translation, so case, "
        "gender and tense come out right at once: «brb» → «I will be back soon», "
        "«afk» → «not at the keyboard», «ty» → «thank you». If the service still "
        "returns «afk» or «gg» in Latin letters, a short Russian variant is put in "
        "its place. Russian abbreviations are expanded the other way: «спс» → "
        "«спасибо», «мб» → «может быть».",
    "Разворачивать сленг и сокращения": "Expand slang and abbreviations",
    "lol, brb, afk, idk, idc, omw, gtg, gg, wp, ez, ty, thx, np, pls, sry,\n"
    "btw, imo, tbh, ngl, rn, asap, wdym, wbu, sup, cya, gn, gm, tmrw, cuz,\n"
    "ppl, rp, ooc, ic и растянутый смех (looool, lmaooo, xD).\n"
    "Обратное направление: спс, пж, нз, мб, крч, ща, оч, тож, збс, норм, прив.":
        "lol, brb, afk, idk, idc, omw, gtg, gg, wp, ez, ty, thx, np, pls, sry,\n"
        "btw, imo, tbh, ngl, rn, asap, wdym, wbu, sup, cya, gn, gm, tmrw, cuz,\n"
        "ppl, rp, ooc, ic and stretched laughter (looool, lmaooo, xD).\n"
        "The other way round: спс, пж, нз, мб, крч, ща, оч, тож, збс, норм, прив.",

    # ---------- Основные: клавиша и текст ----------
    "Горячая клавиша": "Hotkey",
    "Клавиша ловит открытие оверлея. Работает только когда активна игра.":
        "The key opens the overlay. It works only while the game is active.",
    "Вернуть F6": "Back to F6",
    "Открывать это окно при запуске программы": "Open this window at startup",
    "Кликните по полю и нажмите нужное сочетание, например F6 или Ctrl+Alt+T":
        "Click the field and press the combination you want, e.g. F6 or Ctrl+Alt+T",
    "нажмите сочетание клавиш…": "press a key combination…",
    "Текст и маркеры": "Text and markers",
    "Скобки перевода": "Translation brackets",
    "Максимум в сообщении": "Maximum per message",
    "Задержка перевода": "Translation delay",
    "Пауза после последнего символа, перед переводом":
        "Pause after the last keystroke, before translating",
    "Внутри таких скобок текст переводится принудительно: «+привет+» → «Ciao».":
        "Text inside such brackets is translated even in manual mode: «+привет+» → «Ciao».",
    " символов": " characters",
    " мс": " ms",
    " слов": " words",
    " фрагм.": " frag.",

    # ---------- Автоперевод ----------
    "Включить автоперевод": "Enable auto-translation",
    "Как часто переводить: одно сообщение из N":
        "How often to translate: one message in N",
    "Частота": "Frequency",
    "Какое сообщение": "Which message",
    "последнее в серии (каждое N-е)": "the last one (every N-th)",
    "первое в серии": "the first one",
    "случайное в серии": "a random one",
    "Фрагментов в сообщении": "Fragments per message",
    "Длина фрагмента": "Fragment length",
    "Сначала брать фразы из словаря": "Prefer glossary phrases",
    "Слова-паразиты": "Filler words",
    "Слова-паразиты из PDF переводятся в каждом сообщении":
        "Filler words from the PDF are translated in every message",
    "Переводить всегда, вне зависимости от частоты":
        "Always translate, whatever the frequency",
    "Перевод вставляется в обычную русскую речь, чтобы она выглядела живой. "
    "Например: «мне срочно нужна помощь» → «мне срочно нужна Aiutami».":
        "The translation is woven into ordinary Russian speech to make it look "
        "alive. For example: «мне срочно нужна помощь» → «мне срочно нужна Aiutami».",

    # ---------- Чат игры ----------
    "Отправка в игру": "Sending to the game",
    "Вставлять текст в чат игры": "Paste the text into the game chat",
    "Сначала открывать чат игры (клавиша T), потом оверлей":
        "Open the game chat first (key T), then the overlay",
    "Сначала открыть чат игры (T), только потом показать оверлей.\n\n"
    "        Так окружающие в игре видят, что вы пишете, а не стоите без действия.\n"
    "        Пока чат открывается (пауза game_open_delay_ms), оверлей не виден.\n"
    "        ":
        "Open the game chat first (T), show the overlay only after that.\n\n"
        "        That way other players see you are typing, not standing idle.\n"
        "        While the chat is opening (game_open_delay_ms) the overlay stays hidden.\n"
        "        ",
    "Отправлять сразу (Enter в игре)": "Send at once (Enter in the game)",
    "Клавиша чата": "Chat key",
    "Клавиша чата и задержки": "Chat key and delays",
    "После переключения в игру": "After switching to the game",
    "После открытия чата": "After the chat opens",
    "После вставки текста": "After pasting the text",
    "Задержки нужны, чтобы игра успевала открыть чат и вставить текст. Если "
    "сообщения пропадают — увеличьте «после чата».":
        "The delays give the game time to open the chat and paste the text. If "
        "messages go missing, raise the «after chat» delay.",
    "Окружающие видят, что вы печатаете, а не стоите без действия":
        "Other players see you are typing rather than standing idle",

    # ---------- Словарь ----------
    "Язык: —": "Language: —",
    "Язык: %s": "Language: %s",
    "Поиск по фразе или русскому значению…": "Search a phrase or its Russian meaning…",
    "Фраза": "Phrase",
    "Русская запись": "Russian reading",
    "Русские значения (через ;)": "Russian meanings (separated by ;)",
    "Русские значения": "Russian meanings",
    "Добавить фразу": "Add phrase",
    "Удалить": "Delete",
    "Импорт…": "Import…",
    "Экспорт…": "Export…",
    "Вернуть встроенный словарь": "Restore built-in glossary",
    "Фразы-паразиты отмечены «★» — они переводятся в каждом сообщении. Значения — "
    "это то, что вы печатаете по-русски; «е/ё» и «и/й» считаются одной буквой.":
        "Filler phrases are marked with «★» — they are translated in every message. "
        "Meanings are what you type in Russian; «е/ё» and «и/й» count as one letter.",
    "всего фраз: %d": "phrases in total: %d",
    "показано %d из %d": "shown %d of %d",
    " · встроенного словаря нет": " · no built-in glossary",
    "Для этого языка: %s": "For this language: %s",
    "список не задан": "no list set",
    "Для этого языка список не задан.": "No list is set for this language.",
    "Слова-паразиты — ": "Filler words — ",
    "Сначала выберите строку (строки).": "Select a row (or several) first.",
    "Для этого языка русская запись по звучанию не делается — в оверлее "
    "показывается сам текст. Чтение есть только у фраз из словаря.":
        "For this language no Russian reading is produced — the overlay shows the "
        "text itself. Only glossary phrases have a reading.",

    # ---------- Сокращения ----------
    "Поиск по сокращению или развороту…": "Search an abbreviation or its expansion…",
    "Сокращение": "Abbreviation",
    "Разворот (полная фраза)": "Expansion (full phrase)",
    "Разворот": "Expansion",
    "Русский вариант": "Russian variant",
    "Добавить сокращение": "Add abbreviation",
    "Вернуть встроенные": "Restore built-in list",
    "JSON или CSV: сокращение ; разворот ; русский вариант":
        "JSON or CSV: abbreviation ; expansion ; Russian variant",
    "Свои сокращения работают так же, как встроенные, и перекрывают их: «afaik» → "
    "«as far as I know» → «насколько знаю». Во второй колонке — полная фраза на "
    "языке собеседника: её получает переводчик, поэтому падеж и род выходят "
    "верными. В третьей — короткая подстановка, если сервис вернул латиницу. "
    "Кириллическое сокращение («мнепох») идёт в обратную сторону, в текст на "
    "языке сервера. Пустые колонки выключают сокращение.":
        "Your own abbreviations work exactly like the built-in ones and override "
        "them: «afaik» → «as far as I know» → «насколько знаю». The second column "
        "is the full phrase in the other player's language: the translator receives "
        "it, so case and gender come out right. The third one is a short substitute "
        "used when the service returns Latin letters. A Cyrillic abbreviation "
        "(«мнепох») works the other way, into the server language. Empty columns "
        "switch the abbreviation off.",
    "всего сокращений: %d · своих: %d": "abbreviations: %d · yours: %d",
    "В файле не нашлось сокращений.": "No abbreviations found in the file.",
    "Вернуть встроенный список сокращений?\nВаши добавления будут потеряны.":
        "Restore the built-in abbreviation list?\nYour additions will be lost.",

    # ---------- масштаб и проверка ----------
    "Масштаб интерфейса": "Interface scale",
    "Шрифт и отступы окна: %d %%. На маленьком экране поставьте меньше.":
        "Window font and spacing: %d %%. On a small screen choose a lower value.",
    "Размер шрифта и окна настроек. 100 % — обычный; на экране 1366×768 "
    "или при масштабе Windows 150 % удобнее 120–130 %.":
        "Font and settings window size. 100 % is the default; on a 1366×768 screen "
        "or with Windows scaling at 150 % something like 120–130 % is handier.",
    "перевожу… (сервисы заняты)": "translating… (services are busy)",
    "Перевод не удался: %s. Повторите через минуту — проверка попробует "
    "другой сервис, а в чате перевод пойдёт по словарю.":
        "Translation failed: %s. Try again in a minute — the check will use another "
        "service, and in the chat the glossary will be used instead.",

    # ---------- Проверка ----------
    "Проверка перевода": "Translation check",
    "Введите фразу по-русски — увидите, что именно уйдёт в игру и как это читать "
    "вслух. Работает по текущим настройкам окна (до сохранения).":
        "Type a phrase and see exactly what goes to the game and how it reads. It "
        "follows the current settings of this window (before saving).",
    "Направление:": "Direction:",
    "Русский → выбранный язык перевода": "Russian → selected translation language",
    "Ваш язык → русский": "Your language → Russian",
    "Проверить можно оба направления. «Ваш язык → русский» показывает, что "
    "уйдёт в чат игры в режиме для иностранного игрока: сокращения "
    "раскрываются, служебные команды остаются как есть.":
        "Both directions can be checked. «Your language → Russian» shows what the "
        "game chat receives in the foreign player mode: abbreviations are expanded "
        "while service commands stay as they are.",
    "Введите фразу на языке сервера — увидите, что именно уйдёт в чат "
    "игры на русском. Работает по текущим настройкам окна (до сохранения).":
        "Type a phrase in the server language and see exactly what the game chat "
        "receives in Russian. It follows the current settings of this window "
        "(before saving).",
    "например: Слушай, брат, мне срочно нужна помощь":
        "for example: Слушай, брат, мне срочно нужна помощь",
    "например: brb, I'm afk, ty": "for example: brb, I'm afk, ty",
    "Вставить пример": "Insert example",
    "Слова-паразиты текущего языка": "Filler words of the current language",
    "Проверяем обычный режим: в чат уйдёт текст на выбранном языке перевода.":
        "Checking the usual mode: the chat gets text in the chosen translation language.",
    "Проверяем режим для иностранного игрока: в чат уйдёт перевод на русский.":
        "Checking the foreign player mode: the chat gets the Russian translation.",
    "перевожу…": "translating…",
    "Способ: переведено в чат игры": "Result: translated into the game chat",
    "Способ: без перевода (одна команда)":
        "Result: no translation (a single command)",
    "Исходное сообщение: ": "Source message: ",
    "На языке: ": "In the language: ",
    "Способ: ": "Result: ",
    "переведено": "translated",
    "без перевода (только маркеры/команды)": "no translation (markers/commands only)",

    # ---------- сообщения о сохранении и импорте ----------
    "Сохранение": "Saving",
    "Горячая клавиша": "Hotkey",
    "Проверьте горячую клавишу.": "Check the hotkey.",
    "Укажите клавишу.": "Set a key.",
    "Нужна ровно одна клавиша (например, F6 или Ctrl+Alt+T).":
        "Exactly one key is needed (for example F6 or Ctrl+Alt+T).",
    "Одиночная буква/цифра будет мешать печати — добавьте Ctrl/Alt или выберите "
    "F-клавишу.":
        "A single letter or digit would interfere with typing — add Ctrl/Alt or "
        "choose an F-key.",
    "Клавиша «%s» уже занята в игре или в системе.":
        "The key «%s» is already taken by the game or the system.",
    "Импорт": "Import",
    "Экспорт": "Export",
    # ---------- окно настроек: страница «Модули» ----------
    "Модули": "Modules",
    "Каждую часть программы можно выключить. Данные при этом "
    "не теряются: словари, сокращения и настройки остаются "
    "на месте, а программу можно вернуть к полному набору "
    "в любой момент.":
        "Every part of the program can be switched off. No data is lost: "
        "glossaries, abbreviations and settings stay in place, and the full "
        "feature set can be restored at any time.",
    "Включается на странице «%s»": "Switched on the \"%s\" page",
    "Включается на своей странице": "Switched on its own page",
    "Зависит от модуля: ": "Depends on the module: ",
    "Сброс настроек": "Reset settings",
    "Сбросить словарь": "Reset glossary",
    "Сбросить сокращения": "Reset abbreviations",
    "Вернуть все настройки к заводским?\nСловари и горячая клавиша тоже станут "
    "стандартными (F6, итальянский).":
        "Restore all settings to factory values?\nGlossaries and the hotkey also "
        "become standard (F6, Italian).",
    "Не удалось записать config.json:\n": "Could not write config.json:\n",
    "Не удалось записать файл:\n": "Could not write the file:\n",
    "Не удалось прочитать файл:\n": "Could not read the file:\n",
    "Файл не подошёл:\n": "The file did not fit:\n",
    "В файле не нашлось фраз.": "No phrases found in the file.",
    "Загрузить словарь": "Load glossary",
    "Загрузить сокращения": "Load abbreviations",
    "Сохранить словарь": "Save glossary",
    "Сохранить сокращения": "Save abbreviations",
    "Словарь сохранён:\n": "Glossary saved:\n",
    "Сокращения сохранены:\n": "Abbreviations saved:\n",
    "Словари (*.json *.csv *.txt);;Все файлы (*)": "Glossaries (*.json *.csv *.txt);;All files (*)",
    "Сокращения (*.json *.csv *.txt);;Все файлы (*)": "Abbreviations (*.json *.csv *.txt);;All files (*)",
    "Загружено в «%s»: новых %d, обновлено %d.\nНажмите «Сохранить», чтобы применить.":
        "Loaded into «%s»: %d new, %d updated.\nPress Save to apply.",
    "Загружено сокращений: %d (новых %d).\nНажмите «Сохранить», чтобы применить.":
        "Abbreviations loaded: %d (%d new).\nPress Save to apply.",
    "Вернуть встроенный словарь для «%s»?\nВаши добавленные фразы этого языка "
    "будут потеряны.":
        "Restore the built-in glossary for «%s»?\nPhrases you added for this "
        "language will be lost.",
    "в JSON нужен объект «фраза: перевод»":
        "the JSON needs an object «phrase: translation»",
    "в JSON нужен объект «сокращение: разворот»":
        "the JSON needs an object «abbreviation: expansion»",

    # ---------- трей и уведомления ----------
    "Настройки…": "Settings…",
    "Выход": "Exit",
    # ---------- строка состояния оверлея ----------
    "найдена": "found",
    "НЕ найдена": "NOT found",
    "игра: %s": "game: %s",
    "Enter — отправить · Esc — отмена": "Enter — send · Esc — cancel",
    "Enter — отправить без перевода · Esc — отмена":
        "Enter — send without translation · Esc — cancel",
    "В чат уйдёт %d/%d · Enter — отправить · Esc — отмена":
        "Will go to chat %d/%d · Enter — send · Esc — cancel",
    "Ошибка перевода: %s": "Translation error: %s",
    "оригинал": "original",

    "Статус: ваш язык → русский": "Status: your language → Russian",
    "Статус: русский → %s": "Status: Russian → %s",
    "Ваш язык → русский": "Your language → Russian",
    "Русский → %s": "Russian → %s",
    "Режим: ваш язык → русский": "Mode: your language → Russian",
    "Режим: русский → выбранный язык перевода":
        "Mode: Russian → selected translation language",
    "Настройки сохранены. Язык: %s, клавиша: %s.":
        "Settings saved. Language: %s, key: %s.",
    "Клавиша: %s. Язык: %s. Игра: %s.": "Key: %s. Language: %s. Game: %s.",
    "найдена": "found",
    "не найдена": "not found",
    "Оверлей уже запущен (иконка «IT» в трее).":
        "The overlay is already running (the «IT» icon in the tray).",
    "Критическая ошибка": "Critical error",

    # ---------- оверлей ----------
    "Фраза на вашем языке — перевод уйдёт в чат по Enter":
        "Your phrase — the translation goes to the chat on Enter",
    "Текст, +фраза для перевода+, *действие*":
        "Text, +phrase to translate+, *action*",
    "Enter — отправить · Esc — отмена": "Enter — send · Esc — cancel",
    "Enter — отправить без перевода · Esc — отмена":
        "Enter — send without translation · Esc — cancel",
    "Перевожу… отправлю сразу после перевода":
        "Translating… it will be sent right after that",
    "В чат уйдёт ": "The chat gets ",
    "Ошибка перевода: ": "Translation error: ",
    "Ошибка отправки в игру": "Could not send to the game",
    "Не удалось открыть чат игры": "Could not open the game chat",
    "Не удалось закрыть чат игры": "Could not close the game chat",
    "Чат игры открыт, показываю оверлей": "Game chat is open, showing the overlay",
    "Чат игры не открылся, показываю оверлей без него":
        "The game chat did not open, showing the overlay without it",
    "Скопировано в буфер обмена (Ctrl+V).": "Copied to the clipboard (Ctrl+V).",
    " Текст в буфере обмена — вставьте вручную (Ctrl+V).":
        " The text is in the clipboard — paste it manually (Ctrl+V).",
    "Слишком длинно: ": "Too long: ",
    "Готово к отправке: %r": "Ready to send: %r",
    "Оверлей": "Overlay",
    "перевод входящего → русский": "incoming translation → Russian",
}
