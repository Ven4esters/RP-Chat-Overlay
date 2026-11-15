# 📌 Changelog · История версий

Формат: **версия — что изменилось**. Актуальная версия всегда первая.
English version below: [Changelog (English)](#-changelog-english).

---

## 1.6 — 15.11.2026

**Внутренняя переработка: модульность, порядок в коде, двуязычные комментарии.**
Ничего из возможностей не убрано, интерфейс и поведение остались прежними.

### Структура
- Код собран в один пакет **`source/app`**: конфигурация, движок, перевод, словари,
  интерфейс и системные модули лежат рядом, а не в общем каталоге исходников.
- `common.py` переименован в **`app/config.py`** — имя говорит, что внутри: пути,
  журнал, чтение и запись `config.json`, настройки по умолчанию.
- **`app/modules.py`** — реестр модулей: у каждой части программы есть имя, описание,
  ключ в конфигурации, зависимости и раздел настроек, где она включается.
- Настройки по умолчанию собраны в одном месте: служебный словарь `EXTRA` из `main.py`
  больше не дублирует ключи конфигурации.
- В модуле словаря убран устаревший псевдоним `it_to_ru`, в `i18n.py` — лишний импорт,
  файлы приведены к одинаковым переводам строк, у публичных функций появились
  подсказки типов.

### Модули
- В окне настроек появился раздел **«Модули»** — седьмая страница: видно, что можно
  выключить, что от чего зависит и где включается то, у чего уже есть свой переключатель.
- Любую часть можно отключить без вреда для программы: перевод по сети, словарь,
  сокращения, автоперевод, отправка в игру, глобальная клавиша.
- Зависимости соблюдаются сами: без перевода по сети автоперевод тоже считается
  выключенным. Все отключения видны в журнале одной строкой.

### Документация
- Каждый модуль снабжён комментарием на двух языках: русское описание и английское.
- README дополнен таблицей модулей и новой схемой проекта.
- Версия программы — **1.6.0**; готовый exe в `dist` собран из версии 1.5,
  пересобрать можно через `source/build_exe.bat`.

---

## 1.5 — 14.11.2026

**Одно обновление вместо трёх.** Собранное вместе: исправления проверки перевода
(1.4.1) и адаптивного окна (1.4.2) вошли в эту версию, отдельных выпусков для них нет.

### Перевод и сервисы
- **Проверка перевода в режиме «Ваш язык → русский»** действительно переводит на русский:
  окно проверки переключает направление переводчика вместе с выбранным режимом (раньше
  фраза уходила на язык сервера, например на итальянский).
- **Несколько сервисов перевода с подменой:** Google gtx → Google clients5 → Google web →
  MyMemory → Lingva → LibreTranslate. Ответ «429 Too Many Requests» на одном адресе больше
  не останавливает перевод — его берёт второй эндпоинт Google.
- Сервис, ответивший «429», **выключается на 2 минуты**, чтобы не тратить время.
- На всю цепочку отведено **16 секунд**; в окне проверки появляется честная подпись
  «перевожу… (сервисы заняты)», а при неудаче — понятная причина вместо технического текста.
- В режиме «Ваш язык → русский» MyMemory и LibreTranslate не используются (не умеют
  автоопределение языка) — там работают оба эндпоинта Google и Lingva.

### Окно настроек
- **Строка «Скобки перевода» больше не уезжает под соседнюю карточку:** поля `+` и `+`
  получили нормальную высоту, а слой строки отдаётся форме напрямую, без обёртки-виджета.
- **Разделы прокручиваются** (полоса прокрутки справа), поэтому содержимое никогда
  не сжимается и не наезжает само на себя на невысоком экране.
- **Окно адаптивное:** не больше 94 % рабочей области экрана, центрируется при открытии,
  меню разделов сужается вместе с окном.
- **Новый ползунок «Масштаб интерфейса»** (80–180 %) в разделе «Основные»: меняет шрифт
  и размер окна сразу, без перезапуска. Пригодится на 1366×768 и при масштабе Windows 150 %.
- Поля поиска и списки перестали держать жёсткую ширину — подстраиваются под окно.

### Сокращения
- Таблица выросла с **71 до 180 сокращений**: переписка (`ty`, `np`, `tbh`, `ngl`, `afaik`,
  `iirc`, `ttyl`, `hmu`, `lmk`, `tyvm`, `wby`, `wdyt`, `brb`, `bbs`, `omw`, `l8r`, `2moro`, `gr8`…),
  игры (`gg`, `wp`, `ez`, `nt`, `gj`, `glhf`, `op`, `pvp`, `pve`, `npc`, `dps`, `xp`, `lvl`,
  `ult`, `aoe`, `inv`, `acc`, `wtb`, `wts`, `wtt`, `ff`…), ролевой отыгрыш (`rp`, `ooc`, `ic`, `em`, `para`).
- Русских сокращений стало **31**: добавлены `чё`, `щас`, `ваще`, `плз`, `благ`, `пок`, `чел`,
  `инет`, `комп`, `тел`, `др`.
- Опасные для обычного текста токены (`hp`, `mp`, `cd` — «HP ноутбук», «CD-ROM») в таблицу
  не попали, чтобы не портить обычные фразы.

### Локализация
- Переведены на английский новые подписи: масштаб интерфейса, подсказки и сообщения
  проверки, строка состояния оверлея («игра: найдена», «Enter — отправить»), ошибка перевода.

### Документация
- `README.md`: весь функционал сведён в короткое общее описание, добавлен полный
  **английский раздел**.
- Новый **CHANGELOG.md** (на русском и английском).

---

## 1.4 — 14.11.2026

- **Английский интерфейс:** при первом запуске выбор языка (Русский / English), смена в
  настройках без перезапуска. Переведены разделы настроек, подсказки, названия языков,
  меню трея, уведомления и окно оверлея.
- **Свои сокращения:** раздел «Сокращения» по образцу словаря — сокращение, разворот,
  короткий русский вариант, поиск, импорт JSON/CSV, экспорт, возврат встроенных;
  хранится в `data/slang.json`.
- **Проверка перевода в обе стороны:** «Русский → выбранный язык перевода» и
  «Ваш язык → русский».

## 1.3 — 13.11.2026

- **Сленг и сокращения раскрываются до перевода:** «brb» → «I'll be right back» →
  «я скоро вернусь», поэтому падеж, род и время верные.
- Если сервис вернул латиницу, подставляется короткий русский вариант («afk» →
  «не за клавиатурой»).
- Русские сокращения раскрываются в обратную сторону: «спс» → «спасибо», «мб» → «может быть».

## 1.2 — 12.11.2026

- **Короткое меню в трее:** статус переводчика, направление перевода, «Настройки…», «Выход».
  Всё остальное — в окне настроек. Двойной клик по значку открывает оверлей.

## 1.1 — 12.11.2026

- **Режим для иностранного игрока:** любой язык → русский, перевод уходит в чат игры.
- Слова-паразиты переводятся в каждом сообщении.
- Команды `/to /lto /l /wt /s /st` считаются в счётчике автоперевода наравне с обычными.

## 1.0 — 11.11.2026

- Первый выпуск: оверлей с горячей клавишей, 13 языков, словарь с русской записью,
  автоперевод по счётчику и маркерам `+…+`, действия `*…*`, отправка в чат игры,
  трей и окно настроек.

---

# 📌 Changelog (English)

## 1.6 — 2026-11-15

**Internal rework: modularity, code hygiene, bilingual comments.**
No feature was removed; the interface and the behaviour stay the same.

### Structure
- The code now lives in a single package, **`source/app`**: configuration, engine,
  translation, glossaries, interface and system modules sit side by side.
- `common.py` was renamed to **`app/config.py`**, which says what is inside: paths,
  logging, `config.json` reading and writing, default settings.
- **`app/modules.py`** is the module registry: every part of the program has a name,
  a description, a configuration key, its dependencies and the settings page where it
  is switched on.
- The default settings live in one place: the `EXTRA` dictionary in `main.py` no longer
  duplicates configuration keys.
- The obsolete `it_to_ru` alias is gone, an unused import was removed from `i18n.py`,
  line endings are consistent and public functions carry type hints.

### Modules
- A new **Modules** page in the settings window shows what can be switched off, what
  depends on what, and where everything else is configured.
- Every part can be disabled without harming the program: online translation, glossary,
  abbreviations, auto-translation, sending into the game, the global hotkey.
- Dependencies are honoured automatically: with online translation off, auto-translation
  counts as disabled too. Disabled modules are logged on one line at startup.

### Documentation
- Every module is commented in two languages, Russian and English.
- The README gained a module table and a new project layout.
- Program version is **1.6.0**; the ready exe in `dist` was built from 1.5, rebuild it
  with `source/build_exe.bat`.

---

## 1.5 — 14 Nov 2026

**One update instead of three.** The translation-check fix (1.4.1) and the adaptive window
(1.4.2) are both included here — no separate releases for them.

### Translation and services
- The **"Your language → Russian"** direction of the Test window really translates into
  Russian now: the window switches the translator together with the chosen mode (it used
  to send the phrase into the server language, for example Italian).
- **Several translation services with failover:** Google gtx → Google clients5 → Google web →
  MyMemory → Lingva → LibreTranslate. A "429 Too Many Requests" answer on one endpoint no
  longer stops the translation — the second Google endpoint picks it up.
- A service that answered "429" is **cooled down for two minutes** to save time.
- The whole chain has a **16-second budget**; the Test window honestly says
  "translating… (services are busy)" and, on failure, shows a clear reason instead of raw text.
- In the "Your language → Russian" mode MyMemory and LibreTranslate are skipped (no language
  auto-detection) — both Google endpoints and Lingva are used there.

### Settings window
- **The "Translation brackets" row no longer slides under the neighbouring card:** the two
  `+` fields got a proper height and the row layout is given to the form directly.
- **Sections scroll** (scrollbar on the right), so nothing is squeezed or overlapped on a
  short screen.
- **The window is adaptive:** at most 94 % of the screen work area, centred on open, the
  section menu narrows together with the window.
- **New "Interface scale" spin box** (80–180 %) in General: changes the font and window size
  instantly, without a restart — handy on 1366×768 and with Windows scaling at 150 %.
- Search fields and lists no longer have a rigid width.

### Abbreviations
- The table grew from **71 to 180 abbreviations**: chatting (`ty`, `np`, `tbh`, `ngl`, `afaik`,
  `iirc`, `ttyl`, `hmu`, `lmk`, `tyvm`, `wby`, `wdyt`, `brb`, `bbs`, `omw`, `l8r`, `2moro`, `gr8`…),
  gaming (`gg`, `wp`, `ez`, `nt`, `gj`, `glhf`, `op`, `pvp`, `pve`, `npc`, `dps`, `xp`, `lvl`,
  `ult`, `aoe`, `inv`, `acc`, `wtb`, `wts`, `wtt`, `ff`…), roleplay (`rp`, `ooc`, `ic`, `em`, `para`).
- Russian abbreviations: **31**, now including `чё`, `щас`, `ваще`, `плз`, `благ`, `пок`, `чел`,
  `инет`, `комп`, `тел`, `др`.
- Tokens that are common in ordinary text (`hp`, `mp`, `cd` — "HP laptop", "CD-ROM") were left
  out on purpose.

### Localisation
- New English labels: interface scale, Test window hints and messages, overlay status line,
  translation error.

### Documentation
- `README.md`: the whole feature set is condensed into the general description, plus a full
  **English section**.
- New **CHANGELOG.md** in Russian and English.

## 1.4 — 14 Nov 2026

- **English interface:** first run asks for the language (Русский / English), switching in
  Settings is instant. Settings sections, hints, language names, tray menu, notifications
  and the overlay are translated.
- **Own abbreviations:** a glossary-like section — abbreviation, expansion, short Russian
  variant, search, JSON/CSV import, export, restore built-ins; stored in `data/slang.json`.
- **Two-way translation check:** "Russian → selected translation language" and
  "Your language → Russian".

## 1.3 — 13 Nov 2026

- **Slang and abbreviations are expanded before translation:** "brb" → "I'll be right back" →
  «я скоро вернусь», so case, gender and tense come out right.
- If a service returns Latin letters, a short Russian variant is substituted.
- Russian abbreviations are expanded both ways: «спс» → «спасибо», «мб» → «может быть».

## 1.2 — 12 Nov 2026

- **Short tray menu:** translator status, translation direction, "Settings…", "Exit".
  Everything else lives in the settings window. Double click opens the overlay.

## 1.1 — 12 Nov 2026

- **Foreign player mode:** any language → Russian, the translation goes into the game chat.
- Filler words are translated in every single message.
- `/to /lto /l /wt /s /st` count as ordinary messages in the auto-translation counter.

## 1.0 — 11 Nov 2026

- First release: hotkey overlay, 13 languages, glossary with a Russian reading, counter-based
  and marker-based auto-translation, `*actions*`, sending into the game chat, tray icon and
  settings window.
