# DeepLX и Россия: ограничение и обход

> С июня 2025 года DeepL закрыт для российских IP-адресов. Локальный сервис
> DLX работает, но сам DeepL не принимает запросы из России. Ниже — как это
> обойти, чтобы перевод продолжал работать.

## Проблема

При включённом DLX сервис запускается на вашем компьютере и сам пересылает
текст на серверы DeepL. С июня 2025 года DeepL возвращает ошибку `503` для
запросов с российских адресов. В программе это видно как состояние
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

Разверните [`source/tools/deeplx-local`](source/tools/deeplx-local) на сервере
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

> Since June 2025 DeepL is blocked for Russian IP addresses. The local DLX
> service runs, but DeepL itself rejects requests from Russia. Below is how to
> work around it so translation keeps working.

## Problem

With DLX enabled, the service runs locally on your computer and forwards text
to DeepL servers. Since June 2025 DeepL replies with `503` to requests from
Russian addresses. The program shows this as state **«Работает, но DeepL не
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

Deploy [`source/tools/deeplx-local`](source/tools/deeplx-local) on a server
outside Russia (e.g. on Vercel — see `VERCEL.md` next to it). You get an
address like `https://имя-проекта.vercel.app` that translates from a non-Russian
IP without VPN and without `dlx.exe`. Put this address in DLX settings.

### Option 3: disable DLX

If you have no proxy, just disable DLX in settings. The program falls back to
regular translation services (Google, MyMemory, Lingva, LibreTranslate, …) that
work without restrictions.

## Where to find in the program

**Settings → DeepL** → «Your own service address» or «HTTP proxy» field.