# Журнал ошибок и решений / Errors and fixes

Журнал фиксирует проверяемые проблемы проекта: симптом, установленную причину,
решение и регрессионную проверку. Новую запись добавляем после подтверждения
причины; незавершённый инцидент помечаем как открытый, а не записываем догадку
как решение.

This log records verified project failures: symptom, confirmed cause, resolution,
and regression check. Add an entry after confirming the cause; mark an unresolved
incident as open instead of presenting a guess as a fix.

## Записи / Entries

| ID | Проблема и причина | Решение и проверка | Статус |
|---|---|---|---|
| ERR-001 | Текст ролевого чата мог попасть в журналы обычного перевода и отправки. | Логировать метаданные сообщения вместо текста; проверить перевод, отправку и финальный путь оверлея на русском и Windows. См. `test_translator.py`, `test_logging.py`, `test_gamesend_logs.py`, `test_overlay_logs.py`. | Исправлено |
| ERR-002 | Ответ внешнего или собственного DLX-сервиса может содержать произвольное сообщение, в том числе текст запроса; передавать его пользователю без фильтрации небезопасно. | Python-клиент возвращает безопасный код; локальный Node-сервис отдаёт стабильные сообщения и пишет структурированную диагностику без текста запроса. Проверки: `test_dlx_response.py`, `test/server.test.js`. | Исправлено |
| ERR-003 | Состояние `DeepL не отвечает (503)` показывает, что проверка upstream не завершилась успешно; само по себе оно не доказывает региональную блокировку. | Проверить сеть и прокси; при необходимости подключить собственный DLX-сервис или отключить DLX, чтобы использовать резервные переводчики. Инструкция: [`DEEPLX-RUSSIA.md`](DEEPLX-RUSSIA.md). | Причина зависит от upstream; способы диагностики описаны |
| ERR-004 | Длинные названия и описания вариантов анимаций не помещались в карточку и могли перекрывать соседний текст. | Карточки рассчитывают высоту по содержимому, текст переносится, список прокручивается; карточки доступны с клавиатуры и имеют доступные имена. Проверка: `test_animchoice_ui.py`. | Исправлено |
| ERR-005 | Qt UI-тесты пропускались на Linux, если установленный runtime не мог загрузить `libGL.so.1`; Win32 тесты там неприменимы. | Выделить отдельные Linux- и Windows-тесты; Windows CI требует Qt (`RPCHAT_REQUIRE_QT_TESTS=1`) и выполняет Win32 проверки. Локальные пропуски документированы в [`TESTING.md`](TESTING.md). | Исправлено в CI; локальные платформенные пропуски ожидаемы |
| ERR-006 | URL прокси мог содержать пароль в user-info или токен в query-параметре; прежняя маскировка скрывала только user-info. | Перед записью адреса скрывать пароли и чувствительные query-параметры, удалять fragment и сохранять несекретные параметры для диагностики. Проверка: `test_dlx_security.py`. | Исправлено |
| ERR-007 | Ошибки разбора JSON в локальном DLX-сервисе могли возвращать служебный ответ Express вместо понятной ошибки протокола. | Возвращать безопасный JSON с кодом 400/413; журналировать тип события и HTTP-код, не тело запроса. Проверка: `test/server.test.js`. | Исправлено |
| ERR-008 | Переключатель настроек анимировался за 140 мс — немного быстрее интервала 150–300 мс из UI/UX-стандарта. | Установить 160 мс и проверять диапазон регрессией Qt. Проверка: `test_settings_ui.py`. | Исправлено |
| ERR-009 | Windows CI показал, что карточка анимации могла быть ниже естественной высоты раскладки перенесённых описаний (пример: 154 px при подсказке раскладки 188 px). | При изменении размера поднимать минимальную высоту карточки до высоты её раскладки; прокручивать список вместо обрезки текста. Проверка: `test_animchoice_ui.py`. | Исправлено; ждёт повторной проверки в Windows CI |

## Где искать журналы / Where to find logs

Настольное приложение пишет рабочие сообщения в `logs/app.log`, а предупреждения,
ошибки, необработанные исключения и аварийные стеки — в `logs/errors.log`. Если
папка программы недоступна для записи, корень данных переключается на
`%LOCALAPPDATA%\RPChatOverlay` (либо `%APPDATA%\RPChatOverlay`, если
`LOCALAPPDATA` не задан). В обоих случаях журналы находятся в подпапке `logs`.
Отдельный Node.js DLX-сервис пишет JSON-события в консоль; текст перевода,
токены и исходное тело ответа внешнего сервиса не записываются.

The desktop application writes routine messages to `logs/app.log`; warnings,
errors, unhandled exceptions, and crash traces go to `logs/errors.log`. If the
program folder is not writable, its data root falls back to
`%LOCALAPPDATA%\RPChatOverlay` (or `%APPDATA%\RPChatOverlay` when
`LOCALAPPDATA` is unset). In either location, logs are in the `logs` subfolder.
The standalone Node.js DLX service writes JSON events to its terminal output;
translation text, tokens, and raw upstream response bodies are not included.

Перед отправкой журнала проверьте его и удалите адреса, имена пользователей и
другие сведения, которые не нужны для диагностики. Не публикуйте журналы с
данными учётных записей. Приватная отправка уязвимостей сейчас отключена:
[`SECURITY.md`](../SECURITY.md) описывает безопасный порядок запроса частного
контакта без публикации деталей.

Review logs before sharing and remove addresses, usernames, or other details not
needed for diagnosis. Never publish credentials. Private vulnerability
reporting is currently disabled; [`SECURITY.md`](../SECURITY.md) explains how to
request a private contact without publishing sensitive details.
