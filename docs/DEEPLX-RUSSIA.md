# DeepLX и Россия: ограничение и обход

> Если локальный DLX запускается, но перевод получает HTTP `503`, запрос не
> получил успешный ответ от внешнего сервиса. Причина может быть в сети, прокси
> или ответе upstream; код `503` сам по себе не доказывает региональную блокировку.

## Проблема

При включённом DLX сервис запускается на вашем компьютере и сам пересылает
текст на серверы DeepL. При ошибке `503` локальный сервис может быть доступен,
хотя внешний запрос не завершился успешно. В программе это видно как состояние
**«Работает, но DeepL не отвечает (503)»**, а перевод не происходит.

## Как исправить

Используйте **свой HTTP-прокси** или **свой сервер DLX за рубежом**:

### Вариант 1: HTTP-прокси (самый простой)

В настройках DLX укажите адрес своего прокси, например:

| Прокси | Пример адреса |
|---|---|
| v2rayN | `http://127.0.0.1:10809` |
| Clash | `http://127.0.0.1:7890` |
| SOCKS5 | `socks5://127.0.0.1:1080` |

Если прокси требует логин и пароль, укажите их в адресе:
`http://user:pass@127.0.0.1:10809`.

После ввода адреса программа направит запросы к DeepL через прокси, и ошибка
503 исчезнет.

### Вариант 2: свой сервер за рубежом (без dlx.exe)

Разверните [`source/tools/deeplx-local`](../source/tools/deeplx-local/README.md) на сервере
за пределами России (например, на Vercel — см. `VERCEL.md` рядом). Вы получите
адрес вида `https://имя-проекта.vercel.app`, который переводит с зарубежного
IP без VPN и без файла `dlx.exe`. Укажите этот адрес в настройках DLX.

### Вариант 3: отключить DLX

Если прокси нет, просто отключите DLX в настройках. Программа автоматически
вернётся к обычным сервисам перевода (Google, MyMemory, Lingva, LibreTranslate
и другими), которые работают без ограничений.

## Где найти в программе

**Настройки → DeepL** → поле «Адрес своего сервиса» или «HTTP-прокси».

---

## DeepLX and Russia: restriction and workaround

> If local DLX starts but translation receives HTTP `503`, the request did not
> get a successful response from the upstream service. Network, proxy, or
> upstream conditions may be involved; `503` alone does not establish a regional block.

## Problem

With DLX enabled, the service runs locally on your computer and forwards text
to DeepL servers. An HTTP `503` means the upstream request did not complete
successfully; it does not by itself prove a regional restriction. The program
shows this as state **«Работает, но DeepL не
отвечает (503)»**, and no translation occurs.

## How to fix

Use your own **HTTP proxy** or **own DLX server abroad**:

### Option 1: HTTP proxy (easiest)

In DLX settings specify your proxy address, for example:

| Proxy | Example address |
|---|---|
| v2rayN | `http://127.0.0.1:10809` |
| Clash | `http://127.0.0.1:7890` |
| SOCKS5 | `socks5://127.0.0.1:1080` |

If proxy requires login/password, include them in the address:
`http://user:pass@127.0.0.1:10809`.

After entering the address the program routes DeepL requests through the proxy
and error 503 disappears.

### Option 2: own server abroad (without dlx.exe)

Deploy [`source/tools/deeplx-local`](../source/tools/deeplx-local/README.md) on a server
outside Russia (e.g. on Vercel — see `VERCEL.md` next to it). You get an
address like `https://имя-проекта.vercel.app` that translates from a non-Russian
IP without VPN and without `dlx.exe`. Put this address in DLX settings.

### Option 3: disable DLX

If you have no proxy, just disable DLX in settings. The program falls back to
regular translation services (Google, MyMemory, Lingva, LibreTranslate, …) that
work without restrictions.

## Where to find in the program

**Settings → DeepL** → «Your own service address» or «HTTP proxy» field.
