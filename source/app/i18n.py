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
    "Паразит": "Filler",
    "Переводить эту фразу в каждом сообщении":
        "Translate this phrase in every message",
    "Галочка в первой колонке — слово-паразит: фраза переводится в каждом "
    "сообщении, даже когда автоперевод ещё не сработал. Выбор сохраняется "
    "вместе со словарём. Значения — это то, что вы печатаете по-русски; "
    "«е/ё» и «и/й» считаются одной буквой.":
        "The checkbox in the first column marks a filler word: the phrase is "
        "translated in every message, even before auto-translation kicks in. Your "
        "choice is saved with the glossary. Meanings are what you type in Russian; "
        "«е/ё» and «и/й» count as one letter.",
    "Уменьшить значение": "Decrease the value",
    "Увеличить значение": "Increase the value",
    "Настройки сохранены и применены.": "Settings saved and applied.",
    "Несохранённые изменения": "Unsaved changes",
    "В настройках есть неприменённые изменения.\nЗакрыть окно без сохранения?":
        "There are unsaved changes.\nClose the window without saving them?",
    "Закрыть": "Close",
    "Закрыть окно: сохранять для этого не нужно":
        "Close the window: saving first is not needed",
    "Применить настройки (Ctrl+S); окно остаётся открытым":
        "Apply the settings (Ctrl+S); the window stays open",
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
    "Всего: %d\nСвоих: %d": "Total: %d\nOwn: %d",
    "Показано: %d из %d\nСвоих: %d": "Shown: %d of %d\nOwn: %d",
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
    "Проверьте горячую клавишу.": "Check the hotkey.",
    "Укажите клавишу.": "Set a key.",
    "Нужна ровно одна клавиша (например, F6 или Ctrl+Alt+T).":
        "Exactly one key is needed (for example F6 or Ctrl+Alt+T).",
    "Одиночная буква/цифра будет мешать печати — добавьте Ctrl/Alt или выберите "
    "F-клавишу.":
        "A single letter or digit would interfere with typing — add Ctrl/Alt or "
        "choose an F-key.",
    "Импорт": "Import",
    "Экспорт": "Export",
    # ---------------- DeepL рядом (DLX) ----------------
    "DeepL рядом (DLX)": "DeepL alongside (DLX)",
    "DLX — отдельная бесплатная программа с открытым кодом (лицензия MIT), "
    "которая работает на вашем компьютере и переводит через движок DeepL. "
    "Она занимает около 15 МБ и запускается вместе с программой. Текст при "
    "этом уходит на серверы DeepL — так же, как сейчас уходит в Google. "
    "Сервис неофициальный: DeepL может ограничить запросы, и тогда перевод "
    "автоматически вернётся к стандартным сервисам.":
        "DLX is a separate free open-source program (MIT license) that runs on your "
        "computer and translates through the DeepL engine. It takes about 15 MB and "
        "starts together with the app. The text goes to DeepL servers, the same way "
        "it currently goes to Google. The service is unofficial: DeepL may rate-limit "
        "it, and then translation falls back to the standard services automatically.",
    "Переводить через DeepL в первую очередь":
        "Translate through DeepL first",
    "Без этого флажка работает обычная цепочка сервисов":
        "Without this checkbox the regular service chain is used",
    "Запускать сервис вместе с программой":
        "Start the service together with the app",
    "Проверять обновления сервиса при запуске":
        "Check for service updates at startup",
    "Состояние": "State",
    "Проверить": "Check",
    "Запустить": "Start",
    "Остановить": "Stop",
    "Установить": "Install",
    "Обновить": "Update",
    "Удалить сервис": "Remove the service",
    "Короткий запрос к сервису: отвечает ли он":
        "A short request to the service: does it answer",
    "Скачать сервис с GitHub (около 15 МБ)":
        "Download the service from GitHub (about 15 MB)",
    "Доступ к сервису": "Access to the service",
    "Сервис слушает только ваш компьютер. Порт выбирается свободный, а "
    "запросы подписываются токеном, чтобы чужие программы не могли гонять "
    "трафик через ваш DeepL.":
        "The service listens on your computer only. The port is chosen free and "
        "requests carry a token, so other programs cannot push traffic through "
        "your DeepL.",
    "Порт (0 — автоматически)": "Port (0 means automatic)",
    "0 — выбирать свободный порт автоматически":
        "0 — pick a free port automatically",
    "Токен": "Token",
    "Токен знает только программа; в сеть он не уходит":
        "Only the app knows the token; it never leaves the machine",
    "Выпустить новый токен": "Issue a new token",
    "Работает · порт %d": "Running · port %d",
    "Запускается…": "Starting…",
    "Остановлен": "Stopped",
    "Не установлен": "Not installed",
    "Ошибка: %s": "Error: %s",
    " · версия %s": " · version %s",
    "Сервис не подключён к этому окну — перезапустите программу.":
        "The service is not attached to this window — restart the app.",
    "Файлы сервиса: %s": "Service files: %s",
    "Сервис не подключён — перезапустите программу.":
        "The service is not attached — restart the app.",
    "Сервис отвечает нормально.": "The service answers normally.",
    "Сервис не отвечает. Нажмите «Запустить» или «Установить».":
        "The service does not answer. Press Start or Install.",
    "Запустить не удалось: %s": "Could not start: %s",
    "неизвестно": "unknown",
    "Установка сервиса": "Installing the service",
    "Скачать локальный сервис DeepL с GitHub?\n\n"
    "Около 15 МБ, лицензия MIT, файл кладётся рядом с программой.\n"
    "Текст перевода будет уходить на серверы DeepL.":
        "Download the local DeepL service from GitHub?\n\n"
        "About 15 MB, MIT license, the file is placed next to the app.\n"
        "Translation text will go to DeepL servers.",
    "Скачиваю…": "Downloading…",
    "Проверяю…": "Checking…",
    "Проверить выход": "Check the exit",
    "Свой адрес нужен, когда dlx.exe не скачивается или не запускается: сервер из source/tools/deeplx-local (npm start) слушает 1188 и говорит на том же языке, что и DLX. Адрес можно вставить целиком, вместе с /translate — лишний хвост программа отрежет сама.":
        "Your own address is for the case when dlx.exe will not download or "
        "start: the server in source/tools/deeplx-local (npm start) listens on "
        "1188 and speaks the same language as DLX. The address can be pasted "
        "whole, /translate included — the extra tail is trimmed.",
    "не назначена": "not set",
    "см. logs/errors.log": "see logs/errors.log",
    "DeepL рядом": "DeepL alongside",
    "от": "from",
    "до": "to",
    "слов": "words",
    "Русский": "Russian",
    "Слова-паразиты — %s": "Filler words — %s",
    "JSON или CSV: фраза ; русская запись ; значения через ;":
        "JSON or CSV: phrase ; Russian reading ; meanings separated by ;",
    "Пусто — работать через dlx.exe. Адрес своего сервиса — и файл скачивать не нужно":
        "Empty — work through dlx.exe. With your own service address no file is "
        "needed at all",
    "Токен, с которым запущен ваш сервис (TOKEN=…); если он не задан — пусто":
        "The token your service runs with (TOKEN=…); leave empty when it has none",
    "Кому это нужно": "Who needs it",
    "Никому не обязательно. Без DeepL программа переводит через Google и остальные сервисы — так она работает сразу после установки, и большинству игроков этого достаточно. DeepL — это шаг в качестве для тех, кто готов потратить пять минут: либо включите VPN с зарубежным выходом, либо разверните свой сервис и впишите его адрес ниже (как это сделать — VERCEL.md в папке source/tools/deeplx-local). Общий адрес у всех быть не может: DeepL быстро упирается в лимиты частоты, и один перегруженный сервис отказывает всем сразу.":
        "Nobody has to. Without DeepL the program translates through Google and "
        "the other services — that is how it works right after installation, and "
        "for most players that is enough. DeepL is a step up in quality for those "
        "willing to spend five minutes: either switch on a VPN with a foreign exit, "
        "or deploy your own service and put its address below (how to do it — "
        "VERCEL.md in the source/tools/deeplx-local folder). A single shared "
        "address cannot work for everyone: DeepL hits rate limits quickly, and one "
        "overloaded service refuses everybody at once.",
    "Свой адрес сервиса": "Your own service address",
    "Токен своего сервиса": "Your own service token",
    "Своя служба DeepL отвечает — перевожу через неё.":
        "Your own DeepL service answers — translating through it.",
    "Брать прокси из настроек Windows, если свой не задан":
        "Take the proxy from the Windows settings when none is set",
    "VPN в режиме «системный прокси» прописывает адрес в Windows — "
    "сервис будет ходить через него":
        "A VPN in system-proxy mode writes its address into Windows; the service "
        "will go through it",
    "Покажет адрес и страну, из которой выходит прокси (запрос идёт через него)":
        "Shows the address and the country the proxy exits from (the request goes "
        "through it)",
    "Проверяю прокси…": "Checking the proxy…",
    "Прокси не задан — сервис ходит напрямую.":
        "No proxy set — the service goes direct.",
    "Прокси работает. Выход: %s": "The proxy works. Exit: %s",
    "Прокси не годится: %s": "The proxy is not usable: %s",
    "Адрес не подходит: нужен http://, https:// или socks5:// с портом.":
        "The address does not fit: http://, https:// or socks5:// with a port is "
        "needed.",
    "Порт %d — обычно у SOCKS5; сервис сам подставит socks5://.":
        "Port %d usually belongs to SOCKS5; the service will swap socks5:// in.",
    "Если DeepL не отвечает": "When DeepL does not answer",
    "С июня 2025 года DeepL закрыт для российских адресов: сервис DLX "
    "работает, а DeepL отвечает отказом. Своего прокси DLX не поднимает — "
    "он только ходит через тот, что вы укажете, и этот прокси должен "
    "выходить не из России: адрес российского сервера DeepL так же не "
    "примет. Cloudflare WARP и One Client тут не помогут: они не меняют "
    "страну, ближайший узел у них в России. DNS-сервисы вроде NextDNS — "
    "тоже: они только находят адрес по имени, а DeepL смотрит на адрес. "
    "Годится VPN или клиент с "
    "зарубежным выходом, поднявший локальный порт: v2rayN 10809, "
    "Clash 7890, Hiddify 2080, Nekoray 2080. Порт 1080 — обычно SOCKS5, "
    "и программа сама подставит socks5://, если вы написали http://. "
    "Токен DeepL Pro региональную блокировку не снимает — он только для "
    "владельцев подписки и снимает лимиты.":
        "Since June 2025 DeepL is closed for Russian addresses: the DLX service "
        "runs, but DeepL refuses. DLX does not raise a proxy of its own: it only "
        "goes through the one you name, and that proxy has to exit outside Russia — "
        "a Russian server address is refused just the same. Cloudflare WARP and One "
        "Client do not help here: they do not change your country and their nearest "
        "node sits in Russia. DNS services such as NextDNS do not help either: they "
        "only look up an address by name, while DeepL looks at the address itself. A VPN or a client with a foreign exit and a local port "
        "is what works: v2rayN 10809, Clash 7890, Hiddify 2080, Nekoray 2080. Port "
        "1080 usually means SOCKS5, and the program swaps socks5:// in by itself "
        "when you typed http://. A DeepL Pro token does not lift the regional "
        "block; it only removes rate limits for subscribers.",
    "HTTP-прокси": "HTTP proxy",
    "Токен DeepL Pro": "DeepL Pro token",
    "Пусто — подключаться напрямую": "Empty means a direct connection",
    "Пусто — идти напрямую; http, https или socks5":
        "Empty means go direct; http, https or socks5",
    "необязательно": "optional",
    "OAuth-токен DeepL Pro; без него работает бесплатный путь":
        "A DeepL Pro OAuth token; the free route works without it",
    "Работает, но DeepL не отвечает (503)": "Running, but DeepL answers 503",
    "Сервис DeepL запущен, но DeepL не отвечает "
    "(503). Помогает прокси: Настройки → DeepL.":
        "The DeepL service runs, but DeepL answers 503. A proxy helps: "
        "Settings → DeepL.",
    "Сервис установлен и готов к работе.":
        "The service is installed and ready.",
    "Установить не удалось: %s": "Could not install: %s",
    "Удаление сервиса": "Removing the service",
    "Удалить сервис DeepL с диска?\nПрограмма вернётся к обычным "
    "сервисам перевода, настройки останутся.":
        "Remove the DeepL service from disk?\nThe app returns to the regular "
        "translation services, your settings stay.",
    "Перевод получше: DeepL рядом": "Better translation: DeepL alongside",
    "Рядом с программой можно развернуть отдельный сервис перевода — "
    "бесплатную программу DLX с открытым кодом (лицензия MIT).\n\n"
    "· качество DeepL выше, чем у бесплатных сервисов Google;\n"
    "· занимает около 15 МБ и запускается вместе с программой;\n"
    "· текст перевода уходит на серверы DeepL — так же, как сейчас в Google;\n"
    "· сервис неофициальный: DeepL может ограничить запросы, и тогда перевод "
    "сам вернётся к стандартным сервисам;\n"
    "· выключить можно в любой момент: Настройки → DeepL.":
        "You can deploy a separate translation service next to the app — the free "
        "open-source program DLX (MIT license).\n\n"
        "· DeepL quality is higher than the free Google services;\n"
        "· about 15 MB, it starts together with the app;\n"
        "· translation text goes to DeepL servers, as it now goes to Google;\n"
        "· the service is unofficial: DeepL may rate-limit it, and translation then "
        "falls back to the standard services;\n"
        "· you can switch it off at any moment: Settings → DeepL.",
    "Скачать сервис сейчас (около 15 МБ)":
        "Download the service now (about 15 MB)",
    "Остаться на стандартных": "Stay with the standard ones",
    "Включить DeepL": "Enable DeepL",
    "Скачиваю локальный сервис DeepL…": "Downloading the local DeepL service…",
    "Сервис DeepL не установился: %s": "The DeepL service was not installed: %s",
    "Сервис DeepL не установлен — работаю через "
    "стандартные сервисы.":
        "The DeepL service is not installed — using the standard services.",
    "DeepL рядом готов — перевожу через него.":
        "DeepL alongside is ready — translating through it.",
    "Сервис DeepL не запустился (%s) — перевожу через "
    "стандартные сервисы.":
        "The DeepL service did not start (%s) — using the standard services.",
    "Для сервиса DeepL есть версия %s: "
    "Настройки → DeepL → Обновить.":
        "A newer DeepL service is available: %s — "
        "Settings → DeepL → Update.",
    "Локальный сервис DeepL остановлен — перевожу "
    "через стандартные сервисы. Вернуть: "
    "Настройки → DeepL → Запустить.":
        "The local DeepL service has stopped — using the standard services. "
        "To bring it back: Settings → DeepL → Start.",
    "Локальный сервис DeepL снова работает.":
        "The local DeepL service runs again.",

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
    "Русский → %s": "Russian → %s",
    "Режим: ваш язык → русский": "Mode: your language → Russian",
    "Режим: русский → выбранный язык перевода":
        "Mode: Russian → selected translation language",
    "Настройки сохранены. Язык: %s, клавиша: %s.":
        "Settings saved. Language: %s, key: %s.",
    "Клавиша: %s. Язык: %s. Игра: %s.": "Key: %s. Language: %s. Game: %s.",
    "не найдена": "not found",
    "Оверлей уже запущен (иконка «IT» в трее).":
        "The overlay is already running (the «IT» icon in the tray).",
    "Критическая ошибка": "Critical error",

    # ---------- оверлей ----------
    "Фраза на вашем языке — перевод уйдёт в чат по Enter":
        "Your phrase — the translation goes to the chat on Enter",
    "Текст, +фраза для перевода+, *действие*":
        "Text, +phrase to translate+, *action*",
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
    # ---------- модуль «Анимации» / animations module ----------
    "Включить модуль «Анимации»":
        "Enable the Animations module",
    "Клавиша остановки зацикливания":
        "Stop key for a loop",
    "Клавиша, которая прекращает зацикленную анимацию. Нажатие получает и игра, поэтому подойдёт обычная игровая клавиша вроде F.":
        "The key that stops a looped animation. The game receives the press as well, so an ordinary in-game key such as F will do.",
    "Вкл":
        "On",
    "Ключевые слова":
        "Keywords",
    "Зацикливать":
        "Loop",
    "Формы":
        "Forms",
    "Перед вставкой поле ввода чата полностью очищается (Ctrl+A, "
    "Backspace): остаток прошлой строки не приклеится к команде.":
        "Before pasting, the chat input is cleared completely (Ctrl+A, "
        "Backspace), so a leftover from the previous line never sticks to the "
        "command.",
    "Но в игру ничего не уйдёт: ":
        "But nothing will reach the game: ",
    "выключен модуль «Анимации»":
        "the «Animations» module is off",
    "выключен модуль «Отправка в игру»":
        "the «Send into the game» module is off",
    "Строки перетаскиваются мышью — порядок сохраняется вместе со "
    "словарём. Он важен: если у двух фраз одинаковое русское значение, "
    "срабатывает та, что ниже в таблице.":
        "Rows can be dragged with the mouse, and the order is saved with the "
        "glossary. It matters: when two phrases share a Russian meaning, the "
        "lower row wins.",
    "Строки перетаскиваются мышью — порядок запоминается в настройках "
    "и остаётся таким при следующем открытии окна.":
        "Rows can be dragged with the mouse; the order is kept in the settings "
        "and stays that way the next time the window opens.",
    "Строки таблицы перетаскиваются мышью — вместе с правилом едут его "
    "режим, формы, длительность и галочки. Пока строку тянут, она "
    "подсвечена, а синяя линия показывает, куда она встанет. Порядок в "
    "таблице нужен для удобства: в игре анимации играют по порядку слов "
    "в сообщении.":
        "Rows can be dragged with the mouse, and the rule's mode, forms, "
        "duration and checkboxes travel with it. While a row is dragged it is "
        "highlighted, and a blue line shows where it will land. The table order "
        "is for convenience: in the game animations play in the order of the "
        "words in the message.",
    "ПКМ по строке — «Свойства анимации…»: там задаются варианты, если "
    "одному ключу подходят несколько анимаций. Например, ключ «оперся "
    "руками» с вариантами anim_counterleanbar и anim_leanrail: в игре "
    "откроется оверлей выбора с названием и описанием каждого. Один "
    "вариант — обычное правило, оно играет сразу.":
        "Right-click a row and choose Animation properties: that is where the "
        "variants live, for when one keyword fits several animations. Take the "
        "keyword «оперся руками» with the anim_counterleanbar and anim_leanrail "
        "variants: the game shows a chooser with a title and a description for "
        "each. A single variant is an ordinary rule and plays at once.",
    "Пауза после анимации, мс":
        "Pause after an animation, ms",
    "Добавляется к длительности самой анимации, и только потом "
    "запускается следующая из того же сообщения: 1500 мс + 50 мс. "
    "Если из двух ключевых слов играет только первое, увеличьте — "
    "серверу нужно время принять /sa и следующую /anim. "
    "0 — запускать сразу после анимации.":
        "Added to the animation's own length, and only then does the next one "
        "from the same message start: 1500 ms + 50 ms. If only the first of two "
        "keywords plays, raise it — the server needs time to take /sa and the "
        "next /anim. 0 starts it right after the animation.",
    "Не срабатывать на отрицание":
        "Do not fire on negation",
    "Правило молчит, если перед найденным словом стоит «не», «ни», «никогда» и подобное: «открыл зонт» сработает, «не открыл зонт» — нет. Если отрицание есть в самом ключе, проверка для него выключается.":
        "The rule stays silent when «не», «ни», «никогда» or the like stands before the matched word: «открыл зонт» fires, «не открыл зонт» does not. A keyword that already carries a negation switches the check off for itself.",
    "Точно":
        "Exact",
    "Основы":
        "Stems",
    "Леммы":
        "Lemmas",
    "Только та форма, что написана в ключе: «открыл зонт» найдёт «открыл зонт», но не «открывает зонт». Годится для имён и ников.":
        "Only the written form: «открыл зонт» finds «открыл зонт» but not «открывает зонт». Good for names and nicknames.",
    "Любые падежи, числа и спряжения: «открыл», «открывает», «откроет» — одна основа. Без словарей, работает всегда.":
        "Any case, number and conjugation: «открыл», «открывает», «откроет» share one stem. No dictionaries, always available.",
    "Сравнение по словарной форме слова (пакет pymorphy3) и по основе: «люди/человек», «зонта/зонт», «открыл/открывает». Без пакета pymorphy3 работает как «Основы».":
        "Comparison by the dictionary form (the pymorphy3 package) and by the stem: «люди/человек», «зонта/зонт», «открыл/открывает». Without pymorphy3 it works like «Stems».",
    # ---------- варианты анимации и оверлей выбора / variants and the chooser ----------
    "Свойства анимации": "Animation properties",
    "Свойства анимации…": "Animation properties…",
    "Добавить ещё один вариант…": "Add one more variant…",
    "Дублировать правило": "Duplicate rule",
    "Удалить правило": "Delete rule",
    "Ключевые слова: %s": "Keywords: %s",
    "не заданы": "none",
    "Название": "Title",
    "Описание": "Description",
    "Добавить вариант": "Add variant",
    "Удалить вариант": "Remove variant",
    "Готово": "Done",
    "такая анимация уже есть в списке": "that animation is already in the list",
    "Сначала выберите вариант.": "Select a variant first.",
    "Сначала задайте название анимации в таблице.":
        "Set the animation name in the table first.",
    "Заполните варианты: имя для /anim, название и описание. Если "
    "вариантов два и больше, в игре откроется оверлей выбора — игрок "
    "увидит название и описание, а не имя команды. Один вариант — "
    "обычное правило, оно играет сразу.":
        "Fill in the variants: the /anim name, a title and a description. With "
        "two or more variants the game opens a chooser, and the player sees the "
        "title and description instead of the command name. One variant is an "
        "ordinary rule and plays at once.",
    "Группа": "Group",
    "Группа…": "Group…",
    "Группа вариантов": "Variant group",
    "Дать выбранным вариантам общее название группы — в оверлее они встанут "
    "подряд под ним и будут отделены чертой от других групп.":
        "Give the selected variants a common group title — in the chooser they "
        "will sit together under it, separated from other groups by a rule.",
    "Название группы для строк: %d. Пустое поле — убрать группу.":
        "Group title for %d row(s). An empty field removes the group.",
    "Группа необязательна: впишите одинаковое название у нескольких вариантов — "
    "в оверлее они встанут подряд под этим названием, а разные группы будут "
    "разделены чертой.":
        "The group is optional: give several variants the same title and in the "
        "chooser they will sit together under it, while different groups are "
        "separated by a rule.",
    "Выбор анимации": "Animation choice",
    "Какую анимацию играть?": "Which animation should play?",
    "Какую анимацию вы собираетесь использовать?":
        "Which animation are you going to use?",
    "Без описания": "No description",
    "играет": "playing",
    "Ещё меню в очереди: %d — после этого.":
        "Menus still to come: %d, right after this one.",
    "Окно не закроется само: другой вариант можно выбрать в любой момент · Esc — закрыть":
        "The window will not close on its own: you can pick another variant "
        "at any time · Esc closes it",
    "Ничего": "Nothing",
    "Ключ «%s» — какую анимацию играть?": "Keyword «%s» — which animation?",
    "Выбор отправится в чат игры как /anim.":
        "The choice is sent into the game chat as /anim.",
    "выбор из %d: ": "a choice of %d: ",
    "У правила %d варианта(ов) — отправляю первый: /anim %s":
        "The rule has %d variants — sending the first one: /anim %s",
    "Добавить ещё один вариант": "Add one more variant",
    "вариантов анимации не может быть больше 12":
        "there cannot be more than 12 animation variants",
    "Пакет pymorphy3 не найден: уровень «Леммы» сравнивает по основе.":
        "The pymorphy3 package is missing: the «Lemmas» level compares by stem.",
    "Добавить правило":
        "Add rule",
    "Выше":
        "Up",
    "Ниже":
        "Down",
    "Загрузить правила из JSON, созданного кнопкой «Экспорт…»":
        "Load rules from a JSON file made by the Export… button",
    "Проверка правила":
        "Rule check",
    "Например: /me привет":
        "For example: /me hello",
    "Несколько ключевых слов в одном правиле разделяются запятой: «привет, здравствуй». Совпадение ищется целым словом и без учёта регистра, «ё» и «е» считаются одной буквой. Столбец «Формы» решает, как сравнивать слово: «Точно» — ровно написанное, «Основы» — любые падежи и спряжения («открыл» = «открывает»), «Леммы» — по словарю pymorphy3. Одно и то же слово правило запускает один раз, сколько бы раз оно ни повторилось, а каждое своё ключевое слово — отдельным выходом: «да ну, да брось» на «Да ну да брось» сыграет анимацию дважды. Если в одном сообщении совпало несколько правил, анимации играют по очереди, по одной: пока одна на экране, следующая ждёт. Порядок — как в самом сообщении: «Чёрт, я устал *кашляет*» сначала запустит анимацию на «чёрт», потом на «кашляет», даже если в таблице эти правила стоят наоборот. Если один ключ целиком входит в другой, играет только длинный: на «Сел откинувшись» сработает «сел откинувшись», а «сел» промолчит — иначе короткая анимация сразу же погасила бы длинную. Отдельные упоминания в том же сообщении считаются: «Сел откинувшись, а потом сел прямо» запустит обе.":
        "Several keywords in one rule are separated by commas: «привет, здравствуй». A match is a whole word, case-insensitive, and «ё» counts as «е». The «Forms» column decides how a word is compared: «Exact» is the written form, «Stems» covers any case and conjugation («открыл» = «открывает»), «Lemmas» uses the pymorphy3 dictionary. The same word fires a rule once however often it repeats, while every keyword of the rule fires on its own: «да ну, да брось» plays the animation twice on «Да ну да брось». When several rules match one message, the animations play one after another: while one is on screen, the next waits. The order follows the message itself: «Чёрт, я устал *кашляет*» plays the «чёрт» animation first and the «кашляет» one second, even when the rules are listed the other way round. When one keyword sits inside another, only the longer one fires: on «Сел откинувшись» the «сел откинувшись» rule plays and «сел» stays quiet, otherwise the short animation would put the long one out at once. Separate mentions in the same message still count: «Сел откинувшись, а потом сел прямо» plays both.",
    "Правил: %d, готовы к работе: %d, с зацикливанием: %d":
        "Rules: %d, ready to run: %d, looping: %d",
    " · модуль выключен":
        " · module is off",
    "Строка %d: ":
        "Row %d: ",
    "Проверьте правила: ":
        "Check the rules: ",
    "ключевое слово не задано":
        "the keyword is not set",
    "название анимации не задано":
        "the animation name is not set",
    "в названии анимации не должно быть пробелов и косых черт":
        "the animation name cannot contain spaces or slashes",
    "клавиша остановки не задана":
        "the stop key is not set",
    "нужна ровно одна клавиша: буква, цифра, F1–F24 или Space":
        "exactly one key is needed: a letter, a digit, F1–F24 or Space",
    "такая клавиша не поддерживается":
        "that key is not supported",
    "Напишите фразу для проверки.":
        "Type a phrase to check.",
    "без названия":
        "no name",
    "Сработают: ":
        "Will fire: ",
    "Ни одно правило не сработает: в этом режиме ключевого слова в сообщении нет.":
        "No rule will fire: this mode finds no keyword in the message.",
    "Экспорт правил анимаций":
        "Export animation rules",
    "Импорт правил анимаций":
        "Import animation rules",
    "Правила анимаций (*.json);;Все файлы (*)":
        "Animation rules (*.json);;All files (*)",
    'В файле нужен список правил: {"rules": [ … ]}.':
        'The file needs a list of rules: {"rules": [ … ]}.',
    "В файле не нашлось правил.":
        "No rules were found in the file.",
    "Анимации":
        "Animations",
    "Правило в строке %d: %s. Исправьте его или удалите — без этого настройки не сохранятся.":
        "Rule in row %d: %s. Fix or delete it — otherwise nothing is saved.",
    "Правила сохранены в файл ":
        "Rules saved to ",
    "Всегда":
        "Always",
    # ---------- модуль «Анимации»: сообщения / animation module messages ----------
    "Анимация: %s": "Animation: %s",
    "Зацикленная анимация остановлена.": "The looped animation is stopped.",
    "окно игры не найдено": "the game window was not found",
    "отправка в игру выключена в настройках": "sending into the game is switched off",
    "Не удалось отправить команду анимации": "The animation command could not be sent",
    # ---------- модуль «Анимации»: режимы, проверка и состояние / animations ----------
    "/anim":
        "/anim",
    "Режим":
        "Mode",
    "Проверка в игре":
        "Check in the game",
    "Слова проверяются в окне настроек, а отправку видит только игра. Кнопка «Отправить /anim в игру» запускает выбранное правило прямо сейчас — так видно, доходит ли команда: если игра не ответила, причина появится здесь же.":
        "Words are checked in the settings window, but only the game sees the actual sending. The Send /anim into the game button runs the selected rule right now, so you can see whether the command arrives; if the game did not answer, the reason shows up right here.",
    "Отправить /anim в игру":
        "Send /anim into the game",
    "Остановить анимацию":
        "Stop the animation",
    "Доступно, когда настройки открыты из программы":
        "Available when the settings are opened from the running program",
    "Напишите фразу так, как отправили бы её в игру, и посмотрите, какие правила на неё сработают. Здесь проверяются только слова: отправку команд проверяет блок «Проверка в игре» выше.":
        "Type a phrase the way you would send it to the game and see which rules fire. Only the words are checked here: the Check in the game block above tests the sending itself.",
    "Проверка в игре работает, когда настройки открыты из программы.":
        "The in-game check works when the settings are opened from the running program.",
    "Сначала выберите правило с названием анимации.":
        "First select a rule with an animation name.",
    "Название не подойдёт: ":
        "That name will not do: ",
    "Отправляю /anim %s в игру…":
        "Sending /anim %s into the game…",
    "Игра приняла /anim — анимация должна играть.":
        "The game accepted /anim — the animation should be playing.",
    "Не получилось: %s":
        "It did not work: %s",
    "Остановка доступна, когда настройки открыты из программы.":
        "Stopping works when the settings are opened from the running program.",
    "Остановил: отправлен /sa.":
        "Stopped: /sa was sent.",
    "Сейчас играет: %s":
        "Now playing: %s",
    ", зациклено":
        ", looping",
    "Сейчас ничего не играет":
        "Nothing is playing right now",
    "в очереди: %d":
        "in the queue: %d",
    "последняя ошибка: %s":
        "last error: %s",
    "модуль выключен":
        "the module is off",
    "мс": "ms",
    "Действия: /me и *…*":
        "Actions: /me and *…*",
    "Только *…*":
        "Only *…*",
    "Сообщения и /to, /l":
        "Messages and /to, /l",
    "Любое сообщение целиком: и обычное, и команда, и *действия*.":
        "The whole message: plain text, a command and *actions* alike.",
    "Действия: команды /me, /ame, /melow, /melong и текст между *звёздочками* в любом сообщении.":
        "Actions: the /me, /ame, /melow, /melong commands and any text *between asterisks*.",
    "Только текст между *звёздочками*; обычные слова не считаются.":
        "Only the text between *asterisks*; plain words do not count.",
    "Обычные сообщения (вместе с *действиями* внутри них) и команды /to, /lto, /l, /s, /w, /wt. Команды /me не считаются.":
        "Plain messages (with the *actions* inside them) and the /to, /lto, /l, /s, /w, /wt commands. /me commands do not count.",
    "не удалось положить команду в буфер обмена":
        "the command could not be put into the clipboard",
    # ---------- модуль «Анимации»: остановка и слова-синонимы / stopping and synonyms ----------
    "Ключевое слово в вашем сообщении запускает анимацию: в чат игры уходит /anim «название», а через заданное время она останавливается — командой /sa, нажатием клавиши или обоими способами, как выбрано ниже. При зацикливании остановки нет: по истечении того же времени анимация просто запускается снова, пока не нажать клавишу остановки. Длительность 0 мс означает «не останавливать вовсе». Работает только вместе с модулем «Отправка в игру».":
        "A keyword in your message starts an animation: /anim «name» goes into the game chat and the animation is stopped after the configured time — with the /sa command, with a simulated key press or both, as chosen below. With looping on nothing stops it: after the same delay the animation simply starts again until the stop key is pressed. A duration of 0 ms means “never stop”. Works only together with the Sending into the game module.",
    "длительность должна быть от 0 до 600000 мс":
        "the duration must be 0 to 600000 ms",
    "такой режим считывания не поддерживается":
        "that read mode is not supported",
    "Останавливать анимацию командой /sa":
        "Stop the animation with the /sa command",
    "В чат игры уходит /sa — так анимацию гасит сама игра.":
        "The /sa command goes into the game chat, which is how the game itself puts the animation out.",
    "Останавливать анимацию нажатием клавиши F (симуляция)":
        "Stop the animation by pressing the F key (simulated)",
    "Программа нажимает клавишу остановки в игре, как если бы её нажали вы. Клавиша берётся из поля выше.":
        "The program presses the stop key in the game as if you did it. The key comes from the field above.",
    "Останавливать анимацию нажатием клавиши %s (симуляция)":
        "Stop the animation by pressing the %s key (simulated)",
    "Анимация останавливается командой /sa и нажатием «%s».":
        "The animation is stopped with the /sa command and by pressing «%s».",
    "Анимация останавливается командой /sa.":
        "The animation is stopped with the /sa command.",
    "Анимация останавливается нажатием «%s» (симуляция).":
        "The animation is stopped by pressing «%s» (simulated).",
    "Остановка выключена: анимация играет, пока её не сменит другая или пока её не остановит игра.":
        "Stopping is off: the animation plays until another one replaces it or the game stops it.",
    "Клавишу остановки получает и игра, поэтому подойдёт обычная игровая клавиша.":
        "The game receives the stop key as well, so an ordinary in-game key will do.",
    "клавиша остановки не разобрана":
        "the stop key could not be parsed",
    "не удалось переключиться в игру":
        "the game window could not be focused",
}
