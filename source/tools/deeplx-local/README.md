# Локальный DeepL без бинарника · Local DeepL without a binary

**RU.** Небольшой сервер на Node.js, который говорит на языке DLX: те же адреса
(`POST /translate`, `/v1/translate`, `/v2/translate`), тот же формат ответа и
необязательный токен. Нужен, если `dlx.exe` не скачивается или не запускается.

```bash
cd source/tools/deeplx-local
npm install
npm start                 # слушает 0.0.0.0:1188
```

Дальше в программе: **Настройки → DeepL → адрес своего сервиса** →
`http://127.0.0.1:1188`. Если задать `TOKEN=...` в окружении, тот же токен
нужно вписать в настройки программы.

Порт меняется переменной `PORT`, адрес — `HOST`.

Развернуть этот же код на Vercel — инструкция в `VERCEL.md` рядом: получится
свой адрес вида `https://имя-проекта.vercel.app`, который переводит с
зарубежного адреса, без VPN и без файла `dlx.exe`.

**EN.** A small Node.js server that speaks the DLX protocol: same routes
(`POST /translate`, `/v1/translate`, `/v2/translate`), same answer shape, optional
token. Useful when `dlx.exe` cannot be downloaded or will not start.

```bash
cd source/tools/deeplx-local
npm install
npm start                 # listens on 0.0.0.0:1188
```

Then in the program: **Settings → DeepL → your own service address** →
`http://127.0.0.1:1188`. If you set `TOKEN=...`, put the same token into the
program settings. `PORT` and `HOST` change the listen address.

## RU: почему это понадобилось

Старые сборки DeepLX (например `bropines/Deeplx-vercel` → `LegendLeo/deeplx-serverless`,
2024 год) ходят на `www2.deepl.com/jsonrpc` методом `LMT_handle_texts` и
представляются клиентом DeepL для iOS версии 2.9.1. Сегодня DeepL отвечает на
такой запрос текстом «You're using an older version of DeepL. To continue using
the app, please update to the latest version» — вместо перевода. Здесь
используется актуальный путь `oneshot-free.www.deepl.com/v1/translate`, а версия
клиента берётся из открытого App Store lookup, как это делает сам DeepLX.

Ещё одна мелочь, на которой легко потерять вечер: `target_lang` у oneshot
понимается только в нижнем регистре. `IT` молча возвращает английский, `it` —
итальянский.

## EN: why this exists

Older DeepLX builds (e.g. `bropines/Deeplx-vercel` → `LegendLeo/deeplx-serverless`,
2024) call `www2.deepl.com/jsonrpc` with `LMT_handle_texts` and introduce
themselves as DeepL for iOS 2.9.1. Today DeepL answers that with "You're using an
older version of DeepL. To continue using the app, please update to the latest
version" instead of a translation. This server uses the current
`oneshot-free.www.deepl.com/v1/translate` path and resolves the client version
from Apple's open lookup, the way DeepLX itself does.

One more trap: `target_lang` on oneshot is only understood in lowercase. `IT`
silently returns English, `it` returns Italian.

MIT, как и остальные файлы проекта. / MIT, like the rest of the project.
