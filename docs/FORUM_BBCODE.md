[🇷🇺 Русская версия](#russian) | [🇬🇧 English version](#english)

# Форумный пост / Forum post

BBCode внутри блоков готов к копированию: для каждой языковой версии отдельно приведены блок «Что нового?» и основной пост без него. Ссылки на изображения ведут в `main`, поэтому сначала влейте эту ветку: после этого картинки будут доступны по постоянным URL. В разметке постов нет спойлеров, таблиц, якорей и внутренних ссылок; табличная информация вынесена в PNG. По центру стоит только главный баннер; заголовки и текст выровнены по левому краю.

<a id="russian"></a>

## 🇷🇺 Русская версия

### Отдельный BBCode-блок «Что нового?»

```text
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_whats_new_ru.png[/img]
[left]Полный список изменений — в [url=https://github.com/Ven4esters/RP-Chat-Overlay/blob/main/CHANGELOG.md]CHANGELOG.md на GitHub[/url]. Ниже — только основные обновления после версии 1.5.[/left]
[left][b]1.6 — DeepL и DLX.[/b] Добавлен необязательный локальный сервис DeepL: программа устанавливает и запускает его, а при необходимости использует прокси и токен DeepL Pro.[/left]
[left][b]1.7 — собственный DLX.[/b] Можно подключить свой адрес сервиса или развернуть DLX на Vercel; добавлены токен собственного сервиса и более надёжная установка.[/left]
[left][b]1.8 — правила анимаций.[/b] По ключевым словам запускается /anim; настраиваются режимы чтения сообщения, длительность, остановка через /sa или клавишу и зацикливание. Несколько срабатываний в одном сообщении исполняются по очереди.[/left]
[left][b]1.9 — словоформы и точность совпадения.[/b] Для каждого правила можно выбрать «Точно», «Основы» или «Леммы»; добавлены морфологическое сравнение, словарные синонимы и защита от срабатывания на отрицания.[/left]
[left][b]1.10–1.11 — выбор анимации в игре.[/b] Одному ключевому слову можно назначить несколько вариантов с названиями и описаниями. Во время игры появляется меню выбора; варианты можно группировать.[/left]
[left][b]1.12–1.13 — модули и режимы перевода.[/b] Добавлены независимые переключатели модулей с учётом зависимостей и три режима: всё сообщение на язык сервера, только выбранные фрагменты или перевод с языка игрока на русский.[/left]
[left][b]1.14–1.15 — управление правилами.[/b] Похожие правила анимаций можно объединять; добавлены пошаговые отмена и повтор изменений отдельно для словаря, сокращений и анимаций, включая сохранённые данные.[/left]
[left][b]1.16 — сокращения на шести языках.[/b] У каждого языка своя редактируемая таблица; в среднем около 300 сокращений на язык.[/left]
[left][b]1.17 — ручной режим «В машине».[/b] При включении очищается очередь и отправляется один /sa, затем команда анимаций молчит, пока игрок вручную не выключит режим.[/left]
[left][b]1.18 — быстрый ввод ключевых слов.[/b] Оверлей предлагает совпадающие ключи прямо во время набора; список можно листать с клавиатуры. Таблицу правил можно искать, настраивать по высоте и разворачивать на весь экран.[/left]
[left]И другие минорные изменения.[/left]
```

### Основной BBCode-пост

```text
[center][img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/sm_header.png[/img][/center]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_01_ru.png[/img]
[left]RP Chat Overlay — оверлей для ролевого чата в GTA V и FiveM. Переводите сообщения, общайтесь на выбранном языке и запускайте игровые анимации, не отвлекаясь от игры.[/left]
[left]Работает на Windows 10/11. Интерфейс доступен на русском и английском. Обычный релиз — автономный EXE, Python устанавливать не нужно.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_02_ru.png[/img]
[left]• Перевод входящих и исходящих сообщений через онлайн-сервисы; локальный DeepL можно подключить отдельно.[/left]
[left]• Встроенные словари, русская запись произношения и раскрытие сленга до перевода.[/left]
[left]• Автоперевод каждого N-го сообщения и принудительный перевод выделенного фрагмента.[/left]
[left]• Отправка готового текста в игровой чат или копирование в буфер обмена.[/left]
[left]• Запуск анимаций по ключевым словам, команда остановки /sa и ручной режим «В машине».[/left]
[left]• Модули включаются независимо: отключение одной функции не выключает весь оверлей.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_03_ru.png[/img]
[left][b]Из русского в язык сервера.[/b] Пишите по-русски — оверлей подготовит фразу на выбранном языке и покажет русскую запись произношения.[/left]
[left][b]С иностранного на русский.[/b] Переводите сообщение, чтобы понять собеседника; служебные команды и никнеймы не переводятся как обычный текст.[/left]
[left]Автоперевод можно настроить по счётчику сообщений, а отдельный фрагмент — отметить символами +...+.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_04_ru.png[/img]
[left]Доступно 13 языков перевода. Для 11 языков есть встроенные словари; для корейского и арабского доступен онлайн-перевод, а словари можно добавить вручную.[/left]
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_languages_ru.png[/img]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_05_ru.png[/img]
[left]Модули можно включать и отключать в настройках. Если выключить необходимую зависимость, зависимый модуль также считается выключенным. Сводка функций и стартовых значений:[/left]
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_modules_ru.png[/img]
[left]Дополнительно настраиваются язык перевода, режим отправки, клавиша игрового чата, способ ввода, счётчик автоперевода и правила анимаций.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_06_ru.png[/img]
[left][b]Как устроено правило.[/b] Модуль «Анимации» выключен по умолчанию и работает вместе с «Отправкой в игру». Включите модуль и добавьте правило. У каждой строки есть галочка включения, ключевые слова, команда /anim, режим чтения, формы слов, длительность в миллисекундах и зацикливание. Новое правило по умолчанию использует режим «Всегда», формы «Основы», длительность 3000 мс и выключенное зацикливание. Команда задаётся без пробелов и слэшей, например anim_wave; изменения таблицы сохраняются кнопкой «Сохранить».[/left]
[left]Несколько ключей одного правила разделяются запятыми, точками с запятой или новой строкой. Совпадения ищутся по целым словам без учёта регистра; «е» и «ё» считаются одной буквой.[/left]
[left][b]Режим[/b] определяет, какую часть вашего сообщения проверять: «Всегда» — весь текст; «Действия: /me и *…*» — команды /me, /ame, /melow, /melong и текст в звёздочках; «Только *…*» — только текст между звёздочками; «Сообщения и /to, /l» — обычные сообщения и /to, /lto, /l, /s, /w, /wt, но не /me.[/left]
[left][b]Формы — главное отличие режимов поиска.[/b] Это настройка каждой строки правила: она определяет, нужно ли совпасть с точной написанной формой или можно распознать другие формы того же слова.[/left]
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_animation_forms_ru.png[/img]
[left][b]Точно.[/b] Только та форма, которая записана в ключе; подходит для имён, ников и фраз, где важно не расширять совпадение. Многословный ключ ищется без промежуточных слов.[/left]
[left][b]Основы — значение по умолчанию.[/b] Сравнивает основу слова и ловит обычные изменения падежа, числа и спряжения: «открыл», «открывает», «откроет» сопоставляются по основе «откр». Словарь не нужен. В многословной фразе между ключевыми словами допускается одно постороннее слово.[/left]
[left][b]Леммы.[/b] Сравнивает и основы, и словарные формы с помощью pymorphy3. Это помогает с нерегулярными словами: «зонта» ↔ «зонт», «люди» ↔ «человек». Если pymorphy3 недоступен, программа честно переключается на сравнение «Основы» и показывает предупреждение.[/left]
[left][b]Что ещё важно.[/b] Правило срабатывает один раз на одно ключевое слово в сообщении, даже если слово повторено. Разные ключи в одной строке срабатывают отдельно. Если совпало несколько правил, анимации ставятся в очередь и идут по порядку слов в сообщении, а не по порядку строк в таблице. Когда короткий ключ целиком входит в длинный, выбирается более длинное совпадение; отдельное повторное упоминание короткого слова всё равно сработает.[/left]
[left][b]Длительность и остановка.[/b] Длительность новой строки по умолчанию — 3000 мс; допустимый диапазон — 0–600000 мс. По окончании можно отправить /sa, симулировать нажатие выбранной игровой клавиши или использовать оба способа. По умолчанию включён /sa, симуляция клавиши выключена; клавиша остановки зацикливания по умолчанию — F. Значение 0 отправляет /anim один раз и не останавливает и не повторяет анимацию автоматически.[/left]
[left][b]Зацикливание.[/b] Для нового правила оно выключено. Если включить, команда /anim повторяется через выбранную длительность, пока игрок не нажмёт клавишу остановки. Следующая анимация из очереди запускается после завершения текущей и настраиваемой паузы (по умолчанию 50 мс; 0 — без паузы).[/left]
[left][b]Режим «В машине».[/b] Включается только вручную — галочкой в настройках или пунктом меню трея; игра сама состояние транспорта не определяет. При включении очередь очищается, зацикливание прекращается, отправляется ровно один /sa, затем наступает тишина: пока режим включён, не отправляются ни /anim, ни /sa. При выключении старые сообщения не воспроизводятся.[/left]
[left][b]Отрицание и подсказки.[/b] Включённая по умолчанию проверка не даёт сработать на фразы вроде «не открыл зонт»; если отрицание уже входит в сам ключ, проверка для него отключается. Подсказки ключевых слов в оверлее тоже включены по умолчанию: Tab листает варианты, Enter подставляет выбранный ключ, Esc закрывает список.[/left]
[left][b]Проверка и дополнительные варианты.[/b] «Проверить правило» анализирует текст, не отправляя команду в игру; отдельная кнопка отправки /anim проверяет реальный ответ игры. Правила можно перетаскивать, искать, импортировать и экспортировать в JSON. ПКМ по строке открывает «Варианты и свойства»: одному ключу можно назначить несколько анимаций с названиями и описаниями, между которыми игрок выберет в игре.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_07_ru.png[/img]
[left][b]Готовая программа:[/b] скачайте RPChatOverlay.exe только с официальной страницы [url=https://github.com/Ven4esters/RP-Chat-Overlay/releases/latest]GitHub Releases[/url], затем запустите файл. Python не требуется.[/left]
[left]Перед запуском сверьте SHA-256 или MD5 с контрольными файлами, приложенными к тому же релизу. Если сумма не совпадает — не запускайте EXE.[/left]
[left][b]Из исходников:[/b] [url=https://github.com/Ven4esters/RP-Chat-Overlay/archive/refs/heads/main.zip]скачать ZIP проекта[/url], установить Python 3.12 и запустить [code]source/start.bat[/code]. Исходный код: [url=https://github.com/Ven4esters/RP-Chat-Overlay]GitHub[/url].[/left]
[left]Требуются Windows 10/11 и GTA V; для сервисов онлайн-перевода нужно подключение к интернету.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_08_ru.png[/img]
[left]Для опубликованной сборки в README указан отчёт VirusTotal с результатом 2 из 70. Этот результат относится к конкретному хешу файла: сам по себе он не доказывает ни заражение, ни ложное срабатывание. Смотрите точные названия движков и вердиктов в [url=https://www.virustotal.com/gui/file/9a6c8da2e9472ee89ee3a6f6311844ed0a983d00327857a1749dc5782cc34749?nocache=1]отчёте VirusTotal[/url].[/left]
[left]Скачивайте EXE только из официального релиза и обязательно проверяйте контрольную сумму.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_09_ru.png[/img]
[left]С июня 2025 года DeepL недоступен для российских IP-адресов. Локальный DLX может запускаться, но получать от DeepL ошибку 503. Варианты обхода — HTTP-прокси или собственный DLX-сервер за рубежом.[/left]
[left]Пошаговая инструкция: [url=https://github.com/Ven4esters/RP-Chat-Overlay/blob/main/docs/DEEPLX-RUSSIA.md]DeepLX в России[/url]. Если прокси нет, отключите DLX — останутся обычные сервисы перевода.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_10_ru.png[/img]
[left]Лицензия проекта — MIT. Автор: [url=https://github.com/Ven4esters]Ven4esters[/url]. Вопросы и предложения: [url=https://github.com/Ven4esters/RP-Chat-Overlay/issues]GitHub Issues[/url].[/left]
```

<a id="english"></a>

## 🇬🇧 English version

### Standalone “What’s new?” BBCode

```text
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_whats_new_en.png[/img]
[left]The full version history is in [url=https://github.com/Ven4esters/RP-Chat-Overlay/blob/main/CHANGELOG.md]CHANGELOG.md on GitHub[/url]. Below are the major updates since version 1.5 only.[/left]
[left][b]1.6 — DeepL and DLX.[/b] Added an optional local DeepL service that the app can install and launch, with proxy and DeepL Pro token support when needed.[/left]
[left][b]1.7 — your own DLX.[/b] Connect a custom service endpoint or deploy DLX on Vercel; added a token for your own service and more reliable installation.[/left]
[left][b]1.8 — animation rules.[/b] Keywords trigger /anim; configure which message text is checked, duration, stopping with /sa or a key, and looping. Multiple matches in one message run in sequence.[/left]
[left][b]1.9 — word forms and precise matching.[/b] Choose Exact, Stems, or Lemmas for each rule; added morphological matching, glossary-based synonyms, and negation-aware triggers.[/left]
[left][b]1.10–1.11 — in-game animation choices.[/b] Assign multiple named and described variants to one keyword. A chooser appears in game, and variants can be grouped.[/left]
[left][b]1.12–1.13 — modules and translation modes.[/b] Added independent module switches with dependency handling, plus three modes: translate the whole message to the server language, translate marked fragments, or translate the player’s language into Russian.[/left]
[left][b]1.14–1.15 — rule management.[/b] Merge related animation rules; undo and redo edits separately for glossaries, abbreviations, and animations, including saved data.[/left]
[left][b]1.16 — abbreviations in six languages.[/b] Each language has its own editable table, with about 300 entries per language.[/left]
[left][b]1.17 — manual “In a vehicle” mode.[/b] Enabling it clears the queue and sends one /sa; animation commands stay silent until the player switches the mode off manually.[/left]
[left][b]1.18 — faster keyword entry.[/b] Matching keywords are suggested as you type and can be navigated with the keyboard. The rules table is searchable, height-adjustable, and can be expanded full-screen.[/left]
[left]And other minor changes.[/left]
```

### Main forum-post BBCode

```text
[center][img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/sm_header_en.png[/img][/center]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_01_en.png[/img]
[left]RP Chat Overlay is a roleplay chat overlay for GTA V and FiveM. Translate messages, communicate in your chosen language, and trigger in-game animations without leaving the game.[/left]
[left]Runs on Windows 10/11. The interface is available in Russian and English. The regular release is a self-contained EXE; Python is not required.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_02_en.png[/img]
[left]• Translate incoming and outgoing messages with online services; optionally connect a local DeepL service.[/left]
[left]• Use built-in glossaries, Russian pronunciation hints, and slang expansion before translation.[/left]
[left]• Automatically translate every N-th message or force translation of a marked fragment.[/left]
[left]• Send prepared text to the game chat or copy it to the clipboard.[/left]
[left]• Trigger animations by keywords, stop them with /sa, and switch the “In a vehicle” mode manually.[/left]
[left]• Enable or disable modules independently; turning off one feature does not disable the whole overlay.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_03_en.png[/img]
[left][b]Russian to the server language.[/b] Type in Russian; the overlay prepares a message in the selected language and shows a Russian pronunciation hint.[/left]
[left][b]A foreign language to Russian.[/b] Translate a message to understand another player; service commands and nicknames are not translated as ordinary text.[/left]
[left]Set auto-translation to a message counter, or mark a specific fragment with +...+.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_04_en.png[/img]
[left]13 translation languages are available. 11 have built-in glossaries; Korean and Arabic are available for online translation, and custom glossaries can be added.[/left]
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_languages_en.png[/img]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_05_en.png[/img]
[left]Enable or disable modules in Settings. If a required dependency is turned off, the dependent module is treated as disabled too. The image summarizes modules and their defaults:[/left]
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_modules_en.png[/img]
[left]You can also configure the target language, sending mode, game-chat key, input method, auto-translation counter, and animation rules.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_06_en.png[/img]
[left][b]How a rule works.[/b] The Animations module is off by default and requires “Send to game”. Enable the module and add a rule. Each row has an enable checkbox, keywords, an /anim command, a reading mode, word-form matching, a duration in milliseconds, and a loop toggle. New rules default to “Always”, “Stems”, 3000 ms, and looping off. Enter the command name without spaces or slashes, for example anim_wave; save table changes with “Save”.[/left]
[left]Separate keywords in one rule with commas, semicolons, or new lines. Matches are whole-word and case-insensitive; «е» and «ё» count as the same letter.[/left]
[left][b]Mode[/b] selects which part of your message is checked: “Always” — the whole text; “Actions: /me and *…*” — /me, /ame, /melow, /melong and text in asterisks; “Only *…*” — text between asterisks only; “Messages and /to, /l” — plain messages and /to, /lto, /l, /s, /w, /wt, but not /me.[/left]
[left][b]Forms are the key matching setting.[/b] Each rule has its own Forms value. It controls whether a keyword must match the exact written form or whether other forms of the same word can trigger it.[/left]
[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_animation_forms_en.png[/img]
[left][b]Exact.[/b] Matches only the form written in the keyword; useful for names, nicknames, and phrases where broader matching is unwanted. Words in a multi-word keyword must be adjacent.[/left]
[left][b]Stems — the default.[/b] Compares word stems and catches common case, number, and conjugation changes: «открыл», «открывает», and «откроет» match the stem «откр». No dictionary is required. One unrelated word may appear between words in a multi-word keyword.[/left]
[left][b]Lemmas.[/b] Compares stems and dictionary forms using pymorphy3, which helps with irregular words: «зонта» ↔ «зонт», «люди» ↔ «человек». If pymorphy3 is unavailable, the app falls back to Stems and displays a warning.[/left]
[left][b]Other matching rules.[/b] A keyword fires once per message, even if it appears several times. Different keywords in one rule can each fire. When several rules match, animations are queued in the order their words appear in the message, not the table order. If a shorter keyword is fully inside a longer match, only the longer one fires; a separate later mention of the short word still counts.[/left]
[left][b]Duration and stopping.[/b] A new rule defaults to 3000 ms; the allowed range is 0–600000 ms. At the end, the app can send /sa, simulate a chosen game-key press, or use both. /sa is on by default; key simulation is off. The loop stop key defaults to F. A duration of 0 sends /anim once and does not stop or repeat it automatically.[/left]
[left][b]Looping.[/b] It is off for new rules. When enabled, /anim is sent again after each duration until the player presses the stop key. The next queued animation starts after the current one and a configurable tail (50 ms by default; 0 means no extra pause).[/left]
[left][b]“In a vehicle” mode.[/b] It is manual: use the Settings checkbox or tray-menu item; the app does not detect vehicle state. Turning it on clears the queue, breaks looping, sends exactly one /sa, then stays silent: no /anim or /sa is sent while the mode is on. Turning it off does not replay old messages.[/left]
[left][b]Negation and hints.[/b] The default negation check suppresses a match in text such as «не открыл зонт»; if negation is part of the keyword itself, that check is skipped for it. Keyword hints are on by default: Tab cycles suggestions, Enter inserts the selected keyword, and Esc closes the list.[/left]
[left][b]Testing and variants.[/b] “Check rule” tests text without sending a game command; the separate /anim button checks the game’s actual response. Rules can be dragged, searched, imported, or exported as JSON. Right-click a rule and open “Variants and properties” to assign multiple named and described animations to one keyword; the player then chooses in-game.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_07_en.png[/img]
[left][b]Ready-to-run app:[/b] download RPChatOverlay.exe only from the official [url=https://github.com/Ven4esters/RP-Chat-Overlay/releases/latest]GitHub Releases[/url] page, then run it. Python is not required.[/left]
[left]Before running the EXE, verify its SHA-256 or MD5 against the checksum files attached to the same release. Do not run it if the checksum differs.[/left]
[left][b]From source:[/b] [url=https://github.com/Ven4esters/RP-Chat-Overlay/archive/refs/heads/main.zip]download the project ZIP[/url], install Python 3.12, and run [code]source/start.bat[/code]. Source code: [url=https://github.com/Ven4esters/RP-Chat-Overlay]GitHub[/url].[/left]
[left]Requires Windows 10/11 and GTA V. Online translation services require an internet connection.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_08_en.png[/img]
[left]The README links a VirusTotal report with 2 of 70 detections for a specific published file hash. That ratio alone proves neither malware nor a false positive. Check the engine names and verdict labels in the [url=https://www.virustotal.com/gui/file/9a6c8da2e9472ee89ee3a6f6311844ed0a983d00327857a1749dc5782cc34749?nocache=1]VirusTotal report[/url].[/left]
[left]Download the EXE only from the official release and verify its checksum.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_09_en.png[/img]
[left]Since June 2025, DeepL has been unavailable for Russian IP addresses. The local DLX service may start but receive a 503 response from DeepL. Workarounds include an HTTP proxy or your own DLX server hosted abroad.[/left]
[left]Step-by-step guide: [url=https://github.com/Ven4esters/RP-Chat-Overlay/blob/main/docs/DEEPLX-RUSSIA.md]DeepLX in Russia[/url]. If you do not have a proxy, disable DLX to use the regular translation services.[/left]

[img]https://raw.githubusercontent.com/Ven4esters/RP-Chat-Overlay/main/source/images/forum/post_section_10_en.png[/img]
[left]The project is licensed under MIT. Author: [url=https://github.com/Ven4esters]Ven4esters[/url]. Questions and suggestions: [url=https://github.com/Ven4esters/RP-Chat-Overlay/issues]GitHub Issues[/url].[/left]
```
