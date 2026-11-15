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

### Исправления
- **Свой сервис вместо файла.** В настройках появились «Свой адрес сервиса» и
  «Токен своего сервиса»: DeepL можно держать отдельно — на своём компьютере или
  на развёрнутом хосте, — и файл `dlx.exe` тогда не нужен совсем. Адрес
  принимается и целиком, вместе с `/translate`.
- **Развёртывание на Vercel.** В `source/tools/deeplx-local` появились
  `api/translate.js`, `api/index.js` и `vercel.json`, а рядом — инструкция
  `VERCEL.md`: код разворачивается на бесплатном тарифе Vercel за пару минут и
  переводит с зарубежного адреса, без VPN и без файла `dlx.exe`.
- **Сервер `source/tools/deeplx-local`.** Тот же DLX на Node.js: те же адреса,
  тот же формат ответа, необязательный токен, порт 1188. Сделан потому, что
  старые сборки DeepLX 2024 года (в том числе `bropines/Deeplx-vercel`) получают
  от DeepL служебную фразу «You're using an older version of DeepL» вместо
  перевода: у них устаревший путь и версия клиента.
- **Битое скачивание больше не оставляет нерабочий сервис.** Две одновременные
  загрузки писали один файл и портили его — отсюда потом был `WinError 193
  «не является приложением Win32»`. Теперь установка идёт под блокировкой, у
  каждой загрузки свой временный файл, а скачанное проверяется строже: заголовки
  `MZ` и `PE`, а не только первые два байта. Если файл всё-таки испорчен, он
  выбрасывается и скачивается заново автоматически.
- **Занятый порт больше не убивает DeepL.** Раньше один занятый 1188 навсегда
  оставлял сервис выключенным. Теперь порты перебираются (настроенный и три
  свободных рядом), зависший `dlx.exe` на этом порту закрывается, а в состоянии
  видно, на каком порту в итоге работает сервис. Если порт держит чужая
  программа, в журнале будет её имя и PID.
- **Проверка локальных соединений.** Если VPN или файрвол перехватывает даже
  `127.0.0.1`, программа так и говорит: «локальные соединения не работают —
  проверьте VPN и файрвол», вместо восьми секунд молчания.
- **VPN больше не ломает запуск сервиса.** При включённом VPN с системным
  прокси обращения к `127.0.0.1` уходили в этот прокси, и сервис выглядел
  мёртвым: восемь секунд тишины и «не ответил за отведённое время». Теперь все
  локальные запросы идут мимо прокси, а причина молчания называется прямо:
  «порт 1188 открыт, но сервис не отвечает — похоже, локальные запросы
  перехватывает системный прокси или VPN».
- **Прокси из настроек Windows.** DLX — программа на Go и реестр не читает,
  поэтому при VPN в режиме «системный прокси» DeepL видел российский адрес.
  Теперь адрес берётся из Windows автоматически (галочка на странице «DeepL»),
  а в состоянии видно: «через системный прокси 127.0.0.1:2080».
- **Кнопка «Проверить выход».** Показывает адрес и страну, из которой выходит
  прокси, — запрос идёт через сам прокси, поэтому виден его адрес, а не ваш.
  Страна `RU` сразу подписана «выход из России, DeepL такой адрес не примет».
  Поддерживаются http, https и socks5 (в том числе с логином и паролем).
- **Прокси проверяется до запуска.** Программа стучится в прокси сама и смотрит,
  кто отвечает: HTTP-прокси подтверждает `CONNECT`, SOCKS5 — приветствием
  `0x05 0x00`. Поэтому адрес `http://…:1080`, за которым на самом деле SOCKS5,
  больше не вешает сервис: схема подставляется автоматически, а в состоянии
  появляется «прокси распознан как socks5». Недоступный прокси виден сразу:
  «прокси 1.2.3.4:1080 недоступен» вместо восьми секунд тишины.
- **«Запустить не удалось: неизвестно» больше не появляется.** Причина отказа
  терялась: после таймаута сервис гасился, состояние становилось «выключен», и
  окно показывало пустую причину. Теперь причина переживает остановку, а повторный
  запуск сразу после неудачи не долбит сервис по кругу.
- **Адрес прокси проверяется ещё при вводе.** Под полем сразу видно «Адрес не
  подходит: нужен http://, https:// или socks5:// с портом» или подсказка
  «Порт 1080 — обычно у SOCKS5».
- **Сервис DeepL слушает только ваш компьютер.** У DLX по умолчанию адрес
  `0.0.0.0`, то есть он был бы виден всей локальной сети. Теперь программа
  запускает его с `-ip 127.0.0.1`.
- **Отказ DeepL 503 больше не выглядит поломкой.** Если сервис работает, а DeepL
  не отвечает, программа пишет именно это и подсказывает выход. На странице
  «DeepL» появились необязательные поля **HTTP-прокси** и **токен DeepL Pro**:
  из России 503 — обычное дело, и оба поля его снимают. При смене любого из них
  сервис перезапускается сам. В подсказке прямо сказано, что Cloudflare WARP и
  One Client страну не меняют и потому не помогут, а токен DeepL Pro не снимает
  региональную блокировку. Адрес прокси проверяется: `127.0.0.1:10809`
  превращается в `http://127.0.0.1:10809`, а опечатка не попадает в настройки —
  иначе DLX падал бы при запуске с голым кодом 1.
- **Проверка состояния больше не долбит сервис.** Живость проверяется дешёвым
  `GET /`, а не пробным переводом, повторы идут с паузой, а одна и та же ошибка
  пишется в журнал один раз — вместо пятнадцати одинаковых строк подряд.
- **«Сохранить» больше не прячет программу в трей.** На первом запуске окно
  закрывалось после сохранения, и на экране оставался только значок в трее.
  Теперь окно остаётся открытым всегда: шапка «Добро пожаловать» сменяется на
  «Настройки», в подвале появляется «Настройки сохранены и применены», а окно
  поднимается наверх. Закрывает его игрок — кнопкой «Закрыть» или Esc.
- **Согласие на DeepL больше не теряется.** Раньше любое сохранение настроек
  помечало вопрос «уже задан», даже если предупреждение не показывалось.
  Теперь отметка ставится только когда игрок сам включает DeepL галочкой.
- **Кнопка «Сохранить» больше не выглядит нажатой.** Акцентная кнопка была
  серой: фон подвала, заданный стилем родителя, заливал и кнопки. Теперь стиль
  подвала действует только на подвал, акцентная кнопка — ровная заливка без
  светлой рамки, а фокус при открытии окна уходит на список разделов.
- **Окно больше не закрывается при включении DeepL.** Окно согласия создавалось
  в фоновом потоке — Qt так делать нельзя: на первом запуске программа падала
  молча, на втором зависала. Теперь согласие спрашивается в главном потоке, а
  сеть, запуск сервиса и проверка обновлений идут в фоне и отвечают сигналом.
- **Ведётся журнал ошибок `logs/errors.log`.** В него попадают необработанные
  исключения, сбои фоновых потоков, сообщения Qt, стеки при аварийном
  завершении и при зависании главного потока дольше 20 секунд.

### DeepL рядом (DLX)
- **Новый способ перевода — локальный сервис DeepL.** Отдельная бесплатная
  программа DLX (лицензия MIT) работает на компьютере игрока и переводит через
  движок DeepL; включается **только по согласию**: при первом запуске программа
  объясняет, что скачивает, сколько это весит и куда уходит текст.
- **Сервис — первое звено цепочки.** Если он ответил — перевод берётся у него;
  если нет, перевод **сам** уходит к Google, MyMemory, Lingva и LibreTranslate.
  Программа не ломается и не показывает пустой перевод.
- **Полный контроль над процессом.** Программа скачивает и обновляет сервис,
  проверяет готовность коротким запросом при запуске, перезапускает после
  падения (не больше трёх раз за 10 минут), гасит вместе с собой — в том числе
  при аварийном завершении, чтобы не оставлять «сирот».
- **Только локальный доступ.** Сервис слушает `127.0.0.1`, порт выбирается
  свободный, запросы подписываются токеном; токен можно перевыпустить.
- **Честные сообщения.** Если сервис остановили вручную, в трее появляется
  сообщение о том, что часть функционала ограничена, и как её вернуть. Если
  вышла новая версия сервиса — программа предлагает обновиться.
- **Страница «DeepL» в настройках:** состояние, установка, запуск, остановка,
  удаление, порт и токен. Лицензия MIT кладётся рядом с бинарником.

### Интерфейс
- **Счётчики со своими кнопками.** Вместо мелких стрелок Qt — крупные «−» и «+»
  рядом с полем: их видно на тёмной теме, в них легко попасть мышью, а при
  удержании значение меняется подряд. Размер кнопок растёт вместе с масштабом
  интерфейса.
- **Кнопки перерисованы по правилам доступности:** заметная рамка, отдельные
  состояния наведения, нажатия и фокуса для работы с клавиатуры, главная кнопка
  выделена цветом, опасные действия («Удалить», «Сбросить всё») — отдельным
  оттенком. В подвале окна порядок стал обычным: «Закрыть», затем «Сохранить».
- **Слова-паразиты включаются галочкой.** В словаре у каждой фразы появилась
  колонка «Паразит»: галочка заменяет звёздочку «★». Выбор запоминается и больше
  не перезаписывается обновлением встроенного словаря.
- **Счётчик сокращений** — две короткие строки «Всего: 206» и «Своих: 0»:
  подпись больше не разъезжается на три строки в узком окне.
- **«Сохранить» не закрывает окно.** Настройки применяются сразу, в подвале
  появляется подтверждение «Настройки сохранены и применены», а окно остаётся
  открытым — можно править дальше. Ctrl+S делает то же самое; «Закрыть»
  предупредит, если остались неприменённые правки.

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

### Fixes
- **A service of your own instead of the file.** Settings now have "Your own
  service address" and "Your own service token": DeepL can live elsewhere — on
  your machine or on a deployed host — and `dlx.exe` is not needed at all. The
  address is accepted whole, `/translate` included.
- **Vercel deployment.** `source/tools/deeplx-local` gained `api/translate.js`,
  `api/index.js` and `vercel.json`, plus a `VERCEL.md` guide: the code deploys to
  the free Vercel plan in a couple of minutes and translates from a foreign
  address — no VPN, no `dlx.exe`.
- **A `source/tools/deeplx-local` server.** The same DLX on Node.js: same routes,
  same answer shape, optional token, port 1188. It exists because 2024-era DeepLX
  builds (including `bropines/Deeplx-vercel`) get the service phrase "You're using
  an older version of DeepL" from DeepL instead of a translation: their path and
  client version are outdated.
- **A broken download no longer leaves a dead service.** Two simultaneous
  downloads wrote one file and corrupted it, which later surfaced as `WinError 193
  "not a valid Win32 application"`. Installing now runs behind a lock, every
  download gets its own temporary file, and the result is checked properly: the
  `MZ` and `PE` headers, not just the first two bytes. A file that still comes out
  broken is dropped and downloaded again automatically.
- **A busy port no longer kills DeepL.** A single occupied 1188 used to keep the
  service off for good. Ports are now tried in turn (the configured one plus three
  free neighbours), a stuck `dlx.exe` on that port is killed, and the state shows
  which port the service ended up on. When another program holds the port, the log
  names it with its PID.
- **A local connection check.** When a VPN or a firewall intercepts even
  `127.0.0.1`, the program says so — "local connections do not work, check the VPN
  and the firewall" — instead of eight seconds of silence.
- **A VPN no longer breaks the service start.** With a VPN in system-proxy mode,
  calls to `127.0.0.1` went to that proxy and the service looked dead: eight
  seconds of silence and "did not answer in time". Local requests now bypass every
  proxy, and the silence is explained: "port 1188 is open, but the service does not
  answer — the system proxy or VPN seems to intercept local requests".
- **The proxy from the Windows settings.** DLX is a Go program and does not read
  the registry, so with a VPN in system-proxy mode DeepL saw a Russian address.
  The address is now taken from Windows automatically (a checkbox on the DeepL
  page) and the state shows "via the system proxy 127.0.0.1:2080".
- **A "Check the exit" button.** It shows the address and the country the proxy
  exits from; the lookup goes through the proxy itself, so its address is shown
  instead of yours. A `RU` country is labelled "exit from Russia, DeepL will not
  accept such an address". http, https and socks5 (with a login and password too)
  are supported.
- **The proxy is checked before launch.** The program knocks on the proxy itself
  and looks at who answers: an HTTP proxy confirms `CONNECT`, SOCKS5 answers with
  the `0x05 0x00` greeting. An `http://…:1080` address that is really SOCKS5 no
  longer hangs the service: the scheme is swapped automatically and the state says
  "proxy recognised as socks5". A dead proxy is reported at once —
  "proxy 1.2.3.4:1080 is unreachable" instead of eight seconds of silence.
- **"Could not start: unknown" is gone.** The reason was lost: after a timeout the
  service was stopped, the state became "off" and the dialog read an empty reason.
  The reason now outlives the stop, and a repeated start right after a failure no
  longer loops.
- **The proxy address is validated while typing.** A line under the field says
  "The address does not fit: http://, https:// or socks5:// with a port is needed"
  or hints "Port 1080 usually belongs to SOCKS5".
- **The DeepL service now listens on your machine only.** DLX binds `0.0.0.0` by
  default, which would expose it to the whole local network; the program now
  starts it with `-ip 127.0.0.1`.
- **A 503 from DeepL no longer looks like a broken service.** When the service
  runs but DeepL refuses, the program says exactly that and points at the cure.
  The DeepL page gained two optional fields, **HTTP proxy** and **DeepL Pro
  token**: 503 is a common thing from Russia and either field removes it.
  Changing one restarts the service automatically. The hint now states plainly
  that Cloudflare WARP and One Client do not change your country and therefore do
  not help, and that a DeepL Pro token does not lift the regional block. The proxy
  address is validated too: `127.0.0.1:10809` becomes `http://127.0.0.1:10809`, and a typo
  never reaches the settings — otherwise DLX would die at launch with a bare
  exit code 1.
- **The health check no longer hammers the service.** Liveness is checked with a
  cheap `GET /` instead of a trial translation, retries are spaced out, and the
  same error is logged once instead of fifteen identical lines in a row.
- **Save no longer hides the program into the tray.** On the first run the
  window closed after saving and only the tray icon was left. The window now stays
  open every time: the "Welcome" header becomes "Settings", the footer shows
  "Settings saved and applied", and the window is raised to the front. The player
  closes it with Close or Esc.
- **The DeepL consent is no longer lost.** Any settings save used to mark the
  question as "already asked", even when the warning was never shown. The mark is
  now set only when the player ticks DeepL in the settings.
- **The Save button no longer looks pressed.** The accent button was grey: the
  footer background set on the parent widget also painted its children. The
  footer style now targets the footer only, the accent button is a flat fill with
  no light border, and the focus goes to the section list when the window opens.
- **The window no longer closes when DeepL is enabled.** The consent dialog was
  created in a background thread, which Qt forbids: the first start died silently,
  the second one froze. Consent is now asked on the main thread, while the
  network, the service start and the update check run in the background and reply
  through a signal.
- **An error log `logs/errors.log` is kept now.** It collects unhandled
  exceptions, background thread failures, Qt messages, stacks on a hard crash and
  on a main thread frozen for more than 20 seconds.

### DeepL alongside (DLX)
- **A new way to translate: a local DeepL service.** The separate free program DLX
  (MIT license) runs on the player's machine and translates through the DeepL
  engine. It is enabled **only with consent**: at the first start the app explains
  what it downloads, how much it weighs and where the text goes.
- **The service is the first link of the chain.** When it answers, its translation
  is used; otherwise translation **falls back** to Google, MyMemory, Lingva and
  LibreTranslate on its own. The program never breaks and never shows an empty
  translation.
- **Full supervision of the process.** The app downloads and updates the service,
  checks it with a short request at startup, restarts it after a crash (at most
  three times in ten minutes) and shuts it down with the app, including on an
  abnormal exit, so no orphan processes are left behind.
- **Local access only.** The service listens on `127.0.0.1`, a free port is chosen
  automatically and requests carry a token that can be rotated.
- **Honest messages.** If the service is stopped by hand, the tray says that part
  of the functionality is limited and how to bring it back. When a newer service
  version is out, the app offers an update.
- **The DeepL settings page:** state, install, start, stop, remove, port and token.
  The MIT license is stored next to the binary.

### Interface
- **Counters with real buttons.** Small Qt spin arrows are replaced by large
  «−» and «+» buttons next to the field: they are visible on a dark theme, easy to
  hit, and repeat while held. Their size follows the interface scale.
- **Buttons follow accessibility rules:** a clear outline, separate hover, pressed
  and keyboard-focus states, the main action in colour, destructive actions
  («Удалить», «Сбросить всё») in their own tint. The footer now follows the usual
  order: Close, then Save.
- **Filler words are switched by a checkbox.** The glossary gained a «Filler»
  column: a checkbox replaces the «★» mark. The choice is remembered and is no
  longer overwritten by a built-in glossary update.
- **The abbreviation counter** shows two short lines, «Total: 206» and «Own: 0»,
  so the label never breaks into three lines in a narrow window.
- **Save no longer closes the window.** Settings apply at once, the footer confirms
  «Settings saved and applied», and the window stays open for further edits. Ctrl+S
  does the same; Close warns when unsaved changes are left.

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
