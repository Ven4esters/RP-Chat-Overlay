[🇬🇧 English](#english) | [🇷🇺 Русский](#russian)

<a id="english"></a>

# Change log of edits

This file records changes and their reasons so the same problems are not repeated.

---

## 2026-11-15 — Bilingual “What’s new?” forum section

**What changed:** Added a copy-ready RU/EN highlights section to `docs/FORUM_BBCODE.md`, covering major changes from versions 1.6 through 1.18, linking to the full GitHub changelog, and grouping minor changes under a short closing line. Added matching left-aligned RU/EN section-title artwork in the existing dark visual style.

**Artwork:** Updated `source/images/forum/generate_forum_post.py`; generated `post_whats_new_ru.png` and `post_whats_new_en.png` (720×62 each). Existing generated assets were unchanged.

**Checks:** Generator ran with Pillow; verified both artwork files exist, image URLs match local assets, RU/EN sections are present, and the BBCode contains no spoiler/table tags. `git diff --check` passed.

---

## 2026-11-15 — Detailed animation settings and word-form guide

**What changed:** Expanded both forum BBCode versions with a full explanation of animation rule modes, per-rule fields, durations, stopping and looping, the manually controlled in-vehicle silence mode, negation filtering, suggestions, queue order, testing, variants, and import/export. Added bilingual visual cards explaining Exact, Stems, and Lemmas, including the `pymorphy3` fallback.

**Artwork:** Regenerated the bilingual section-header set and added `post_animation_forms_ru.png` / `post_animation_forms_en.png`. All 28 forum PNG assets are generated from the script. The forum BBCode still contains no unsupported table/spoiler/anchor markup.

**Checks:** `ruff check source`, `ruff format --check source`, generator `py_compile`, `git diff --check`, and RU/EN BBCode validation (all 28 image links resolve locally; tag nesting and forbidden-markup checks pass).

---

## 2026-11-15 — Bilingual forum BBCode and refreshed artwork

**What changed:** Added `docs/FORUM_BBCODE.md` with copy-ready RU and EN forum posts. The posts use only supported-style BBCode for text, links and images: no spoilers, tables, internal anchors, or intra-post links. All section headers are left-aligned; only the main title banner is centered. Table content is rendered as PNG images.

**Artwork:** Added `source/images/forum/generate_forum_post.py` and localized hero, section-header, module-summary, and language-summary images. Asset URLs in the BBCode target the stable `main` branch, so merge the assets before posting.

**Reference:** The target thread content could not be retrieved; a shortened route returned the forum index. The redesign follows the user-provided original header image and the existing forum artwork in the repository.

**Checks:** Regenerated all 24 localized PNG assets; verified all BBCode image paths and markup; `ruff check source`, `ruff format --check source`, `py_compile` for the generator, and `git diff --check` passed.

---

## 2026-11-15 — Recent README and license updates

**Commits:** `8d3b608`, `dc9ed6a`, `f1248c9`, `0ed4fe4`, `72bc046`, `a9634cd`, `2b053b0`.

1. **Separate EN/RU heading references.** English heading images are 1000×150 with large text; Russian images are 720×48 and displayed at 670 px. `source/images/forum/generate_readme_heads.py` generates localized images.
2. **No duplicate Contents heading.** Removed the duplicate text heading from `README.ru.md`; kept the list of links.
3. **VirusTotal.** Added a localized section about the 2/70 result, plausible heuristic factors (not claiming to know the exact two verdicts without their engine labels), SHA-256 verification, and the official download source.
4. **“Module system” / «Система модулей».** Renamed the section in both READMEs; updated images, alt text, anchors, and table-of-contents links; removed duplicate text H2 headings.
5. **Language switch links.** Added a link to the opposite-language README at the beginning of each file.
6. **DeepLX in the English README.** Replaced a Russian quote for the 503 status with the English UI wording: “Running, but DeepL answers 503”.
7. **Full MIT license.** Added the missing `LICENSE` file with the canonical English text, included the complete text in `README.md`, and added a Russian translation to `README.ru.md`, noting that the English text is authoritative.
8. **Bilingual change log.** Added this complete English section, language links at the top, and stable language anchors; retained the Russian history below.
9. **Main replacement preflight.** Fetched the full remote history to establish the common base; compared the current branch tree with `main`. The branch removes only the obsolete `branch-develop.bat` from the main tree. Ruff 0.17.6 reported formatter drift, so 40 Python files were formatted before the PR; all checks and 48 tests then passed.
10. **CI security-report fix.** The PR CI tried to upload Bandit JSON as SARIF, causing validation failure and preventing the pip-audit report from being generated. Removed the invalid SARIF uploads and now retain both scanner JSON reports as a regular Actions artifact.

**Checks:** Compared the English license text in the README with `LICENSE`; checked localized image links and dimensions; `ruff check source`, `ruff format --check source`, 48 tests, and `git diff --check` passed.
**Status:** Completed, committed, and pushed.

---

## 2026-11-15 — DeepL translator widget bugs (commits 72323a9, cc9718a)

### Fix 1: `dlx.translate()` remained stuck on “Translating…”
**Cause:** `dlx.translate()` sent `source_lang: "auto"` to DeepL, which does not accept that value. For automatic detection, omit `source_lang`.
**Fix:** In `source/app/dlx.py`, do not add `source_lang` to the JSON when `source == "auto"`.
**Status:** Fixed, committed, and pushed.

### Fix 2: “Clear” did not re-enable “Translate”
**Cause:** `_dlx_clear` did not call `setEnabled(True)` on the Translate button.
**Fix:** Added `self.b_dlx_translate.setEnabled(True)` to `_dlx_clear`.
**Status:** Fixed, committed, and pushed.

### Fix 3: Translation watchdog timer
**Cause:** If `dlx.translate()` never returned (the service accepted the connection but did not respond), the button and “Translating…” state remained stuck indefinitely.
**Fix:** Added a 15-second `QTimer` in `source/app/settings_ui.py`; on timeout it resets the state, enables the button, and displays an error. Added RU and EN i18n strings.
**Status:** Fixed, committed, and pushed.

### Revert (commit `dd3ab57`)
Reverted all DeepL translator widget changes (`settings_ui.py`, `dlx.py`, `i18n.py`) to the state before `d7916c7`. Kept only the `start.bat` fix.

---

## 2026-11-15 — `start.bat` failed to run from sources (commit `da32bf9`)

### Fix 1: `set "PYEXE="`
**Cause:** In Windows CMD, `set "VAR="` leaves the variable defined with an empty value, so `if defined PYEXE` returns `true`. Python 3.12 discovery was skipped, `.venv` was not created, and the script exited without launching the app.
**Fix:** Removed `set "PYEXE="`.
**Status:** Fixed, committed, and pushed.

### Fix 2: `if defined PYTMP` in `:try_py`
**Cause:** The same issue: `set "PYTMP="` leaves the variable defined, and the empty value caused a false call to `:try`.
**Fix:** Replaced the check with `if not "%PYTMP%"==""`.
**Status:** Fixed, committed, and pushed.

---

## 2026-11-15 — Bilingual README (commits `abca90d`, `7c76bd9`, `f41c534`, `2619ec5`, `ebefc94`, `b762f5d`, `0bc045a`)

### Change 1: Initial README
**What:** Replaced the old, overly long `README.md` with a concise version (87 lines) and created `README.ru.md` with matching layout.
**Structure:** H1 and subtitle, license badge, contents, About, Features, Tech Stack, Requirements, Installation, Quick Start, Configuration, Contributing, License, Contacts.
**Status:** Committed and pushed.

### Change 2: Badges
**What:** Added badges after H1 for Windows, Python, languages, abbreviations, EXE, VirusTotal, and MIT.
**Status:** Committed and pushed.

### Change 3: Revisions from review feedback
**What:** Removed empty badge links; styled headings with emoji; removed unsupported settings (position/transparency); clarified that animations are not limited to `*...*`; split Windows and GTA 5 requirements; removed the Contributing section; added the DeepLX-in-Russia note and `docs/DEEPLX-RUSSIA.md`; documented translation modes, `+...+`, `*...*`, filler words, and glossary priority.
**Status:** Committed and pushed.

### Change 4: Rendered heading images
**What:** Replaced text headings with project-style images (dark panel, accent stripe, white text) and generated localized image pairs.
**Issue:** Text in the images was vertically misaligned.
**Fix:** The generator uses `anchor="lm"` (left, middle) to vertically center the text, following the reference image.
**Status:** Committed and pushed.

### Change 5: Consistency and follow-up feedback
**What:** Used a rendered heading for Contents without a duplicate text heading. Added blank paragraph spacing before rendered headings. Replaced “Quick Start” with the full settings/module-system section, describing configuration options in plain language.
**Status:** Completed; the later rename to “Module system” / «Система модулей» is recorded above.

---

## Working rules learned during the work

1. **`set "VAR="` in `start.bat`:** Never initialize a variable to an empty value before `if defined`; CMD treats the empty variable as defined.
2. **Text in rendered headings:** Use `anchor="lm"` for vertical centering instead of manually calculating `text_y`.
3. **DeepL widget revert:** Use commit `90aa58a` as the revert base (the state before `d7916c7`).
4. **Heading image sizes:** Follow the language-specific references: EN 1000×150 with large text; RU 720×48, displayed at 670 px. Generator: `source/images/forum/generate_readme_heads.py`.
5. **README headings:** Do not duplicate a rendered image heading with a text H2; put `<a id="..."></a>` before each image for table-of-contents navigation.

---

## STYLEGUIDE / CONTRIBUTING compliance review

Current status:

| Requirement | Status | Notes |
|---|---|---|
| Clean-code principles | Partial | RU/EN comments exist, but not all functions have complete test coverage. |
| Formatter and linter in CI | Complete | `.github/workflows/ci.yml` runs Ruff lint and format checks. |
| Naming conventions | Yes | PascalCase for classes, snake_case for functions, UPPER_SNAKE_CASE for constants. |
| README documentation | Yes | Bilingual README pair with rendered headings. |
| Public function docstrings | Partial | Present in many modules, but not everywhere. |
| Error handling | Yes | Shared handling through `DlxError` and `TranslateError`. |
| Logging | Yes | `setup_logging`; application logs in `logs/app.log`. |
| Security | Yes | CI runs Bandit SAST, pip-audit SCA, and TruffleHog secret scanning. |
| Tests | Yes | 48 deterministic, network-free unit tests across 8 test modules. |
| CI quality gates | Yes | Checks are defined in `.github/workflows/ci.yml`. |
| Code review / PR | Yes | `CONTRIBUTING.md`, PR template, and Conventional Commits. |
| Dependencies and configuration | Yes | `requirements.txt`; `config.py` validates configuration at startup. |
| Definition of Done | Yes | STYLEGUIDE section 8 and the PR template checklist. |

Remaining partial items are test coverage and public docstring coverage; the project infrastructure and CI checks are in place.

---

[🇬🇧 Back to English](#english) | [🇷🇺 Русская версия](#russian)

<a id="russian"></a>

# Справка о правках

Этот файл фиксирует внесённые правки и их причины, чтобы не наступать на одни и те же грабли повторно.

---

## 2026-11-15 — Подробно об анимациях и словоформах

**Что изменено:** В русскую и английскую версии форумного BBCode добавлено подробное описание режимов анализа сообщений, полей правила, длительности, остановки и зацикливания, ручного режима тишины «В машине», отрицаний, подсказок, очереди, проверок, вариантов и импорта/экспорта. Добавлены двуязычные карточки «Точно / Основы / Леммы» с пояснением резервного режима без `pymorphy3`.

**Графика:** Перегенерирован двуязычный комплект заголовков, добавлены `post_animation_forms_ru.png` / `post_animation_forms_en.png`. Все 28 изображений форума создаются скриптом; в BBCode по-прежнему нет неподдерживаемых таблиц, спойлеров и якорей.

**Проверки:** успешно прошли `ruff check source`, `ruff format --check source`, `py_compile` генератора и `git diff --check`; проверены RU/EN-блоки BBCode, вложенность тегов, отсутствие запрещённой разметки и существование всех ссылок на изображения.

---

## 2026-11-15 — Двуязычный BBCode для форума и новая графика

**Что изменено:** Добавлен `docs/FORUM_BBCODE.md` с готовыми к копированию русским и английским вариантами поста. Используется BBCode для текста, ссылок и изображений; в публикациях нет спойлеров, таблиц, якорей и внутренних ссылок. Заголовки разделов выровнены влево, по центру расположен только главный баннер. Содержимое таблиц вынесено в PNG.

**Графика:** Добавлен генератор `source/images/forum/generate_forum_post.py` и набор RU/EN-баннеров, заголовков, сводок модулей и языков. Ссылки на изображения в BBCode ведут в стабильную ветку `main`, поэтому перед публикацией нужно влить файлы.

**Источник оформления:** Содержимое нужной темы получить не удалось: короткая ссылка возвращает главную страницу форума. Обновление основано на присланном изображении старой шапки и существующей графике форума в репозитории.

**Проверки:** заново сгенерированы все 24 локализованных PNG; проверены ссылки на изображения и разметка BBCode; прошли `ruff check source`, `ruff format --check source`, `py_compile` генератора и `git diff --check`.

---

## 2026-11-15 — Последние уточнения двуязычного README и лицензии

**Коммиты:** `8d3b608`, `dc9ed6a`, `f1248c9`, `0ed4fe4`, `72bc046`, `a9634cd`, `2b053b0`.

1. **Разные эталоны заголовков для EN и RU.** Английские изображения — 1000×150, крупный текст; русские — 720×48, отображаемая ширина 670 px. Генератор `source/images/forum/generate_readme_heads.py` создаёт отдельные локализованные изображения.
2. **Содержание без дубля.** Убран дублирующий текстовый заголовок «Содержание» в `README.ru.md`; список ссылок сохранён.
3. **VirusTotal.** Добавлен отдельный локализованный раздел о результате 2/70, вероятных эвристических причинах (с оговоркой, что конкретные два вердикта без меток движков подтвердить нельзя), проверке SHA-256 и официальном источнике загрузки.
4. **«Система модулей» / “Module system”.** Переименован заголовок в обеих версиях, заменены изображения, alt-тексты, якоря и ссылки оглавления; дублирующие текстовые H2 удалены.
5. **Переключение языка.** В начале каждого README добавлена ссылка на противоположную языковую версию.
6. **DeepLX в английском README.** Русская цитата статуса 503 заменена на английский текст интерфейса “Running, but DeepL answers 503”.
7. **Полный текст MIT.** Добавлен отсутствовавший файл `LICENSE` с каноническим английским текстом; полный текст включён в `README.md`, русский перевод — в `README.ru.md` с пояснением, что английский вариант является исходным.
8. **Двуязычный журнал изменений.** Добавлен полный английский раздел, ссылки на оба языка в начале файла и якоря для перехода; русская история сохранена ниже.
9. **Проверка полной замены main.** Загружена полная удалённая история для определения общего предка, сравнен состав файлов текущей ветки и `main`. Ветка удаляет из дерева main только устаревший `branch-develop.bat`. Ruff 0.17.6 обнаружил расхождения форматирования, поэтому перед PR отформатированы 40 Python-файлов; после этого проверки прошли, все 48 тестов успешны.
10. **Исправление CI-отчётов безопасности.** CI пытался загрузить JSON Bandit как SARIF, из-за чего проверка формата падала и `pip-audit` не успевал создать отчёт. Удалена некорректная SARIF-загрузка; JSON-отчёты обоих сканеров сохраняются обычным Actions artifact.

**Проверки:** английский текст лицензии в README сравнен с `LICENSE`; ссылки на локализованные изображения и их размеры проверены; успешно пройдены `ruff check source`, `ruff format --check source`, 48 тестов и `git diff --check`.
**Статус:** выполнено, закоммичено и отправлено.

---

## 2026-11-15 — Ошибки виджета DeepL-переводчика (коммиты 72323a9, cc9718a)

### Правка 1: dlx.translate() зависал на «Перевожу…»
**Причина:** `dlx.translate()` отправлял `source_lang: "auto"` в DeepL, но DeepL не принимает такое значение. Для автоопределения параметр `source_lang` нужно опускать.
**Исправление:** В `source/app/dlx.py` параметр `source_lang` не добавляется в JSON, когда `source == "auto"`.
**Статус:** исправлено, закоммичено, отправлено.

### Правка 2: Кнопка «Очистить» не включала «Перевести» обратно
**Причина:** `_dlx_clear` не вызывал `setEnabled(True)` для кнопки перевода.
**Исправление:** Добавлен `self.b_dlx_translate.setEnabled(True)` в `_dlx_clear`.
**Статус:** исправлено, закоммичено, отправлено.

### Правка 3: Сторожевой таймер на перевод
**Причина:** Если `dlx.translate()` никогда не возвращался (сервис принял соединение, но не отвечал), кнопка и «Перевожу…» зависли навсегда.
**Исправление:** В `source/app/settings_ui.py` добавлен `QTimer` на 15 с; по истечении — сброс состояния, включение кнопки, сообщение об ошибке. Добавлена строка i18n (RU + EN).
**Статус:** исправлено, закоммичено, отправлено.

### Откат (коммит `dd3ab57`)
Все изменения виджета DeepL-переводчика (`settings_ui.py`, `dlx.py`, `i18n.py`) откачены к состоянию до `d7916c7`. Оставлено только исправление `start.bat`.

---

## 2026-11-15 — `start.bat` не запускался из исходников (коммит `da32bf9`)

### Правка 1: `set "PYEXE="`
**Причина:** В Windows CMD `set "VAR="` создаёт переменную с пустым значением, но `if defined PYEXE` возвращает `true`. Из-за этого поиск Python 3.12 пропускался, `.venv` не создавался, скрипт закрывался без запуска.
**Исправление:** Убрана строка `set "PYEXE="`.
**Статус:** исправлено, закоммичено, отправлено.

### Правка 2: `if defined PYTMP` в `:try_py`
**Причина:** Та же проблема — `set "PYTMP="` делает переменную определённой, пустая строка приводила к ложному вызову `:try`.
**Исправление:** Заменено на `if not "%PYTMP%"==""`.
**Статус:** исправлено, закоммичено, отправлено.

---

## 2026-11-15 — Двуязычный README (коммиты abca90d, 7c76bd9, f41c534, 2619ec5, ebefc94, b762f5d, 0bc045a)

### Правка 1: Начальный README
**Что:** Заменён старый раздутый `README.md` на краткий вариант (87 строк) и создан `README.ru.md` с идентичным оформлением.
**Структура:** H1 + подзаголовок, бейдж лицензии, оглавление, О проекте, Возможности, Стек, Требования, Установка, Быстрый старт, Конфигурация, Как внести вклад, Лицензия, Контакты.
**Статус:** закоммичено, отправлено.

### Правка 2: Отрисованные бейджи
**Что:** Добавлен блок бейджей сразу после H1 (Windows, Python, языков, сокращений, EXE, VirusTotal, MIT).
**Статус:** закоммичено, отправлено.

### Правка 3: Переработка по замечаниям
**Что:** Убраны лишние скобки у бейджей, заголовки стилизованы эмодзи, убраны несуществующие настройки (положение/прозрачность), анимации не только `*...*`, требования разделены (Windows и GTA 5), удалён раздел «Как внести вклад», добавлена пометка про DeepLX в России + `docs/DEEPLX-RUSSIA.md`, добавлен раздел режимов перевода (`+...+`, `*...*`, слова-паразиты, приоритет Словаря).
**Статус:** закоммичено, отправлено.

### Правка 4: Изображения-заголовки вместо текста
**Что:** Все H2/H3 заменены на изображения в стиле проекта (тёмная панель, акцентная полоса, белый текст). Сгенерированы локализованные пары изображений.
**Баг:** Текст в изображениях уплывал вниз.
**Исправление:** Генератор переведён на `anchor="lm"` (left, middle) — текст по вертикальному центру, как на эталонном изображении.
**Статус:** закоммичено, отправлено.

### Правка 5: Единообразие и новые замечания
**Что:** «Содержание» — только отрисованным заголовком без дублирующего текста. Перед каждым отрисованным заголовком — абзац расстояния (пустая строка). «Быстрый старт» заменён полноценным разделом настроек с информацией о системе модулей и описаниями параметров на человеческом языке.
**Статус:** завершено; последующее переименование заголовка в «Система модулей» / “Module system” записано выше.

---

## Правила, выработанные в процессе работы

1. **`set "VAR="` в start.bat** — никогда не инициализировать переменную пустым значением перед `if defined`; CMD считает пустую переменную определённой.
2. **Текст в отрисованных заголовках** — всегда использовать `anchor="lm"` (left, middle) для вертикального центрирования, не ручной расчёт `text_y`.
3. **Откат DeepL-виджета** — при откате использовать коммит `90aa58a` как базу (состояние до `d7916c7`).
4. **Размеры изображений-заголовков** — размеры зависят от языка и эталона: EN 1000×150 с крупным текстом, RU 720×48 (отображение 670 px), генератор `source/images/forum/generate_readme_heads.py`.
5. **README** — не дублировать текстовый H2 под отрисованным изображением; якоря `<a id="..."></a>` ставятся перед каждым изображением для навигации по оглавлению.

---

## Проверка проекта на соответствие STYLEGUIDE / CONTRIBUTING

Текущее состояние:

| Требование | Статус | Комментарий |
|---|---|---|
| Базовые принципы чистоты кода | Частично | Есть комментарии RU + EN, но не все функции полностью покрыты тестами. |
| Единый formatter/linter в CI | Выполнено | `.github/workflows/ci.yml` запускает Ruff lint и format checks. |
| Стиль именования | Да | PascalCase для классов, snake_case для функций, UPPER_SNAKE_CASE для констант. |
| Документация README | Да | Двуязычная пара README с отрисованными заголовками. |
| Докстринги публичных функций | Частично | Есть во многих модулях, но не везде. |
| Обработка ошибок | Да | Единая модель через `DlxError`, `TranslateError`. |
| Логирование | Да | `setup_logging`; логи приложения в `logs/app.log`. |
| Безопасность | Да | В CI запускаются Bandit SAST, pip-audit SCA и TruffleHog для поиска секретов. |
| Тесты | Да | 48 детерминированных unit-тестов без сети в 8 тестовых модулях. |
| CI quality gates | Да | Проверки определены в `.github/workflows/ci.yml`. |
| Code Review / PR | Да | `CONTRIBUTING.md`, PR template и Conventional Commits. |
| Зависимости и конфигурация | Да | `requirements.txt`; `config.py` проверяет конфигурацию при запуске. |
| Definition of Done | Да | Раздел 8 в STYLEGUIDE и чек-лист PR template. |

Неполными остаются покрытие тестами и полнота докстрингов; инфраструктура проекта и CI-проверки настроены.

---

[🇬🇧 English version](#english) | [🇷🇺 К началу русской версии](#russian)
