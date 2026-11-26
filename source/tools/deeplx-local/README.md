# Локальный сервис DeepL / Local DeepL service

**RU.** Сервер на Node.js, совместимый с DLX. Он предоставляет локальной
сборке RP Chat Overlay интерфейс DLX, если `dlx.exe` недоступен.

**EN.** A Node.js server compatible with DLX. It provides the local RP Chat
Overlay build with the DLX interface when `dlx.exe` is unavailable.

## Содержание / Contents

- [Русский](#русский)
  - [Возможности](#возможности)
  - [Запуск](#запуск)
  - [Безопасность](#безопасность)
- [English](#english)
  - [Features](#features)
  - [Run locally](#run-locally)
  - [Security](#security)

## Русский

### Возможности

- Node.js 18 или новее; используется Express и `axios`.
- Адрес по умолчанию: `http://127.0.0.1:1188`.
- Совместимые запросы: `POST /translate`, `POST /v1/translate` и
  `POST /v2/translate`.
- Проверка доступности: `GET /`.
- Необязательная авторизация Bearer-токеном через переменную `TOKEN`.
- Перевод выполняется через современный oneshot API DeepL; сервису нужен
  интернет-доступ.

### Запуск

Из корня репозитория перейдите в папку сервиса и установите зависимости:

```sh
cd source/tools/deeplx-local
npm ci
npm start
```

Сервер слушает порт `1188`. В RP Chat Overlay откройте **Настройки → DeepL**,
включите использование своего DLX-сервиса и укажите
`http://127.0.0.1:1188`.

Параметры окружения:

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `HOST` | `127.0.0.1` | Адрес прослушивания |
| `PORT` | `1188` | Порт сервера |
| `TOKEN` | пусто | Bearer-токен для защиты запросов |

По умолчанию сервер слушает только локальный компьютер (`127.0.0.1`). Для
доступа с других устройств задайте `HOST=0.0.0.0`, настройте Bearer-токен и
правила брандмауэра. Если задан `TOKEN`, добавьте тот же токен в настройки
собственного DLX-сервиса в приложении.

Для развёртывания на Vercel см. [VERCEL.md](VERCEL.md).

### Безопасность

По умолчанию сервер привязывается к `127.0.0.1`, поэтому принимает только
локальные подключения. Для доступа с других устройств задайте `HOST=0.0.0.0`,
обязательно настройте Bearer-токен и правила брандмауэра. Не публикуйте токен и
не добавляйте его в репозиторий. Текст переводов передаётся сервису DeepL.

## English

### Features

- Node.js 18 or later; uses Express and `axios`.
- Default URL: `http://127.0.0.1:1188`.
- Compatible endpoints: `POST /translate`, `POST /v1/translate`, and
  `POST /v2/translate`.
- Health check: `GET /`.
- Optional Bearer-token authentication through the `TOKEN` environment variable.
- Translation uses DeepL's modern oneshot API; the service needs internet access.

### Run locally

From the repository root, enter the service directory and install dependencies:

```sh
cd source/tools/deeplx-local
npm ci
npm start
```

The server listens on port `1188`. In RP Chat Overlay, open **Settings → DeepL**,
enable your own DLX service, and enter `http://127.0.0.1:1188`.

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Address to listen on |
| `PORT` | `1188` | Server port |
| `TOKEN` | empty | Bearer token to protect requests |

By default, the server listens only on the local computer (`127.0.0.1`). To
accept connections from other devices, set `HOST=0.0.0.0`, configure a Bearer
token and firewall rules. If `TOKEN` is set, enter the same token in the app's
custom DLX service settings.

For deployment to Vercel, see [VERCEL.md](VERCEL.md).

### Security

By default, the server binds to `127.0.0.1` and accepts local connections only.
To allow other devices, set `HOST=0.0.0.0`, configure a Bearer token and firewall
rules. Do not publish the token or add it to the repository. Translation text is
sent to DeepL.

## Tests / Тесты

Run the protocol and error-response tests with Node.js 18 or later:

```sh
npm ci
npm test
```

Tests use a loopback ephemeral port and a stub translator; they do not contact
DeepL or include real chat text.

## License

This service is distributed under the repository's [MIT License](../../../LICENSE).
