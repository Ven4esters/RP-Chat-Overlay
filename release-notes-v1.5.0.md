# 1.5.0 — адаптивное окно и надёжный перевод

Текущая версия: оверлей-переводчик чата для GTA V и FiveM. Первый выпуск на GitHub — дальше версия будет только расти.

## Что нового

- **Окно настроек адаптируется под экран.** Разделы прокручиваются, окно занимает не больше 94 % рабочей области и центрируется при открытии. Строка «Скобки перевода» больше не уезжает под соседнюю карточку.
- **Масштаб интерфейса от 80 до 180 %.** Меняется сразу, без перезапуска — для ноутбуков с разрешением 1366×768 и масштаба Windows 150 %.
- **Перевод не зависит от одного сервиса.** Цепочка: Google → второй адрес Google → MyMemory → Lingva → LibreTranslate. Сервис, ответивший «слишком много запросов», исключается на две минуты, на всю попытку отведено 16 секунд. Если перевести не удалось, окно называет причину, а текст можно отправить как есть.
- **Проверка перевода переключает направление вместе с режимом,** поэтому «Ваш язык → русский» и «Русский → выбранный язык перевода» проверяются каждое в свою сторону.
- **Сокращения: 180 иностранных и 31 русское** вместо 71. Переписка, игры и ролевой отыгрыш. Сокращение раскрывается до перевода, поэтому падеж, род и время получаются верными.
- **README переписан:** весь функционал в коротком описании плюс полная английская версия. Добавлен `CHANGELOG.md` на русском и английском.

## Установка

1. Скачайте `RPChatOverlay.exe` из вложений этого выпуска.
2. Положите в любую папку и запустите — устанавливать нечего, Python и библиотеки внутри файла.
3. При первом запуске программа спросит язык интерфейса: русский или English.

Windows 10 и 11, 64 бита. Если игра запущена от имени администратора, запускайте оверлей тоже от администратора.

Windows может предупредить, что издатель не проверен: это обычная реакция на программы, собранные PyInstaller. «Подробнее» → «Выполнить в любом случае».

## Файл

| Параметр | Значение |
| --- | --- |
| Файл | `RPChatOverlay.exe` |
| Версия | 1.5.0.0 |
| Размер | 39 268 114 байт (37,4 МиБ) |
| MD5 | `99648a90c173504c9b95ce6794748319` |
| SHA-256 | `47d81b8109ff9a926571508b7437e1b8765dd66e6504f6500584bad92ac2e3fb` |

Проверить файл: **https://www.virustotal.com/gui/file/47d81b8109ff9a926571508b7437e1b8765dd66e6504f6500584bad92ac2e3fb**

Свои контрольные суммы на Windows: `certutil -hashfile RPChatOverlay.exe SHA256`.

## Ссылки

- Полный список изменений: [CHANGELOG.md](https://github.com/Ven4esters/RP-Chat-Overlay/blob/main/CHANGELOG.md)
- Описание программы и скриншоты: [README.md](https://github.com/Ven4esters/RP-Chat-Overlay/blob/main/README.md)
- Исходный код: папка [`source`](https://github.com/Ven4esters/RP-Chat-Overlay/tree/main/source)

---

# 1.5.0 — adaptive window, reliable translation

The current version: a chat translator overlay for GTA V and FiveM. This is the first GitHub release; the version number will only grow from here.

## What's new

- **The settings window adapts to the screen.** Sections scroll, the window takes at most 94 % of the work area and is centred when it opens. The translation brackets row no longer slides under the neighbouring card.
- **Interface scale from 80 to 180 %.** Applied instantly, without a restart — useful on 1366×768 laptops and with Windows scaling at 150 %.
- **Translation no longer depends on a single service.** The chain is Google → a second Google endpoint → MyMemory → Lingva → LibreTranslate. A service that answers "too many requests" is excluded for two minutes, and the whole attempt has a 16-second budget. If nothing worked, the window names the reason and the text can still be sent as it is.
- **The test window switches the direction together with the mode,** so "Your language → Russian" and "Russian → chosen language" are each checked in their own direction.
- **Abbreviations: 180 foreign and 31 Russian** instead of 71. Chatting, gaming and roleplay. An abbreviation is expanded before translation, so case, gender and tense come out right.
- **README rewritten:** the whole feature set in a short description plus a full English version. A new `CHANGELOG.md` in Russian and English.

## Installation

1. Download `RPChatOverlay.exe` from the assets of this release.
2. Put it in any folder and run it — there is nothing to install, Python and every library are packed inside the file.
3. On the first run the program asks for the interface language: Russian or English.

Windows 10 and 11, 64-bit. If the game runs as administrator, run the overlay as administrator too.

Windows may warn that the publisher is unknown: this is normal for programs built with PyInstaller. Choose "More info" and then "Run anyway".

## File

| Parameter | Value |
| --- | --- |
| File | `RPChatOverlay.exe` |
| Version | 1.5.0.0 |
| Size | 39 268 114 bytes (37.4 MiB) |
| MD5 | `99648a90c173504c9b95ce6794748319` |
| SHA-256 | `47d81b8109ff9a926571508b7437e1b8765dd66e6504f6500584bad92ac2e3fb` |

Verify the file: **https://www.virustotal.com/gui/file/47d81b8109ff9a926571508b7437e1b8765dd66e6504f6500584bad92ac2e3fb**
