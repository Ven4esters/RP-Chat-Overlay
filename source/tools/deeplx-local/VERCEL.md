# Как развернуть DeepLX на Vercel · Deploying DeepLX on Vercel

**RU.** Инструкция для папки `source/tools/deeplx-local` из этого проекта. После
развёртывания у вас будет свой адрес вида
`https://имя-проекта.vercel.app`, который переводит через DeepL **с зарубежного
адреса**, — VPN для этого не нужен, а файл `dlx.exe` не нужен вообще.

**EN.** A guide for the `source/tools/deeplx-local` folder of this project. Once
deployed you get an address like `https://your-project.vercel.app` that
translates through DeepL **from a foreign IP** — no VPN needed, and no
`dlx.exe` at all.

---

## RU: что понадобится

- аккаунт GitHub (бесплатный) и аккаунт Vercel (бесплатный, входит через GitHub);
- Node.js 18+ на компьютере — только чтобы сделать первый коммит, если
  пойдёте через GitHub. Для способа с Vercel CLI он тоже нужен;
- ничего платить не надо: тариф Hobby бесплатный и подходит для личных проектов.

Что именно заливать: **содержимое папки `source/tools/deeplx-local`**, а не весь
проект. В ней уже лежит всё нужное:

```
api/translate.js    перевод (POST /api/translate)
api/index.js        проверка живости (GET /api/)
translate.js        сам перевод через DeepL
vercel.json         маршруты и время жизни функции
package.json        зависимость axios
server.js           локальный запуск, на Vercel не используется
```

---

## Способ 1: через GitHub (без командной строки на Vercel)

### 1. Положить папку в свой репозиторий

На github.com: **New repository** → имя, например `deeplx`, тип **Public** или
**Private** (любой), **Create repository**. Затем на своём компьютере:

```bash
cd "RP Chat Overhaul/source/tools/deeplx-local"
git init
git add .
git commit -m "DeepLX for Vercel"
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/deeplx.git
git push -u origin main
```

`node_modules` в репозиторий не попадёт: он уже в `.gitignore`.

### 2. Импортировать репозиторий в Vercel

1. Зайдите на **vercel.com** → **Sign up** → **Continue with GitHub**.
2. **Add New… → Project** → найдите свой репозиторий `deeplx` → **Import**.
3. На экране настройки:
   - **Framework Preset** — `Other`;
   - **Root Directory** — оставить `./` (если репозиторий — это сама папка);
   - **Build Command** — оставить пустым (переключатель **Override** включать не надо);
   - **Output Directory** — пусто;
   - **Environment Variables** — пока ничего, токен добавим на шаге 4.
4. **Deploy**. Сборка занимает меньше минуты.

Готово: Vercel покажет адрес `https://имя-проекта.vercel.app`.

> Если вы залили в репозиторий **весь проект** (а не только папку), то в
> **Settings → General → Root Directory** укажите
> `source/tools/deeplx-local` и нажмите **Redeploy**.

### 3. Проверить, что работает

Откройте в браузере:

```
https://имя-проекта.vercel.app/api/translate
```

Должен прийти ответ:

```json
{"code":200,"message":"DeepLX on Vercel is running. POST text + target_lang here.","method":"Free"}
```

Это значит, что функция жива. Теперь проверим сам перевод (PowerShell или
терминал):

```bash
curl -X POST "https://имя-проекта.vercel.app/api/translate" ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"Привет, как дела?\",\"source_lang\":\"RU\",\"target_lang\":\"IT\"}"
```

Ждём `"data":"Ciao, come va?"`. Если пришло `"data":"You're using an older
version of DeepL…"` — вы развернули не эту папку, а старый репозиторий
`bropines/Deeplx-vercel`: в нём мёртвый протокол, он так и отвечает.

### 4. Поставить токен (обязательно)

Без токена ваш адрес — открытая дверь: любой, кто его узнает, будет переводить
через ваш лимит.

1. Придумайте длинную случайную строку, например
   `openssl rand -hex 24` или просто 40 случайных символов.
2. Vercel → ваш проект → **Settings → Environment Variables** → **Add New**:
   - **Key**: `TOKEN`
   - **Value**: ваша строка
   - **Environments**: `Production` (можно и `Preview`)
3. **Save**, затем **Deployments → ⋯ у последнего деплоя → Redeploy**.
   Переменные окружения применяются только к новому деплою — без перезапуска
   токен не заработает.

---

## Способ 2: без GitHub, через Vercel CLI

```bash
npm install -g vercel
cd "RP Chat Overhaul/source/tools/deeplx-local"
vercel login          # откроется браузер, войдите тем же аккаунтом
vercel                # первый запуск: вопросы про проект, отвечайте Enter
vercel --prod         # боевой адрес
```

CLI сам спросит имя проекта и предложит настройки по умолчанию — они подходят.
Токен добавляется так:

```bash
vercel env add TOKEN production     # вставьте строку, Enter
vercel --prod                       # передеплой, чтобы токен применился
```

---

## Подключить к программе

**Настройки → DeepL → «Свой адрес сервиса»**:

```
https://имя-проекта.vercel.app
```

или полный адрес — `https://имя-проекта.vercel.app/api/translate`, программа
сама отрежет хвост `/translate`.

**«Токен своего сервиса»** — та же строка, что вы записали в `TOKEN`.

Дальше — **Сохранить**. Окно не закроется, а состояние сервиса сменится на
«свой сервис имя-проекта.vercel.app». Файл `dlx.exe` при этом не нужен: если он
у вас уже скачан, его можно удалить вместе с папкой `data\dlx`, программа
больше к нему не обращается.

Проверить, что адрес принят: на странице DeepL нажмите **«Проверить»**.

---

## Что важно знать

- **Адрес публичный.** `https://имя-проекта.vercel.app` доступен всем, у кого он
  есть. Токен из шага 4 — единственная защита, поэтому не оставляйте его пустым.
- **Это тот же DeepL.** Сервер просто пересылает текст и получает перевод с
  адреса Vercel (обычно США или ЕС), поэтому региональный запрет перестаёт
  мешать. Ничего «взломанного» тут нет, но и гарантий нет: DeepL может
  ограничить частоту запросов.
- **Лимиты Hobby**: время функции по умолчанию 10 с (в `vercel.json` поднято до
  30 с), 100 ГБ трафика в месяц, бесплатный тариф — только для личных проектов.
  Одному игроку этого хватает с большим запасом.
- **Холодный запуск.** Первый запрос после простоя может занять 1–2 секунды.
  Программа даёт на пробный перевод 5 секунд, так что это не мешает, но первый
  перевод в сессии может быть чуть медленнее.
- **Регион функции** меняется в **Settings → Functions → Region**. Для DeepL
  разумнее европейский (`fra1`, Франкфурт) — ближе к серверам DeepL. На Hobby
  доступен один регион.
- **Логи.** Vercel → проект → **Logs** (или `vercel logs https://имя-проекта.vercel.app`).
  Причина отказа DeepL пишется туда строкой `DeepLX-vercel: 503 — …`.
- **Если приходит 429.** Значит, DeepL притормозил этот адрес: у Vercel адреса
  общие. Помогает подождать, сменить регион функции или указать свой токен
  DeepL Pro (в поле «Токен DeepL Pro» в программе — он уходит в запросе).
- **Если `vercel.app` не открывается из вашей сети** — привяжите свой домен:
  **Settings → Domains → Add**, и используйте его в настройках программы.
- **Проверка защиты деплоя.** Если браузер просит логин Vercel при открытии
  адреса, включена **Deployment Protection**: **Settings → Deployment
  Protection** → для Production выберите **Disabled**, затем Redeploy.
- **Свой экземпляр — своя ответственность.** Не раздавайте адрес публично:
  чужие запросы съедят лимиты и могут привести к блокировке адреса DeepL.

---

## Короткая версия (для тех, кто уже всё знает)

```bash
cd "RP Chat Overhaul/source/tools/deeplx-local"
git init && git add . && git commit -m "DeepLX for Vercel"
git remote add origin https://github.com/ЛОГИН/deeplx.git && git push -u origin main
# vercel.com → Add New → Project → Import → Framework: Other → Deploy
# Settings → Environment Variables → TOKEN=… → Redeploy
curl -X POST https://имя-проекта.vercel.app/api/translate \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer ТОКЕН' \
  -d '{"text":"Привет","source_lang":"RU","target_lang":"IT"}'
# в программе: Настройки → DeepL → Свой адрес сервиса → https://имя-проекта.vercel.app
```

---

## EN: the same thing in brief

1. Push the **contents of `source/tools/deeplx-local`** to a GitHub repository.
2. vercel.com → **Add New → Project** → import the repo → **Framework Preset:
   Other**, build command empty, root directory `./` (or
   `source/tools/deeplx-local` if you pushed the whole project) → **Deploy**.
3. Open `https://your-project.vercel.app/api/translate` in a browser: you should
   see `{"code":200,...}`. Then POST a test text.
4. Add an environment variable `TOKEN` (Settings → Environment Variables) and
   **Redeploy** — without a token your endpoint is open to anyone.
5. In the program: **Settings → DeepL → "Your own service address"** =
   `https://your-project.vercel.app`, **"Your own service token"** = the same
   `TOKEN`. Save. No `dlx.exe` needed any more.

Hobby plan: 30 s function limit (set in `vercel.json`), 100 GB bandwidth a month,
personal projects only. Pick the Frankfurt region for a shorter path to DeepL.
Reasons for failures land in Vercel → Logs as `DeepLX-vercel: <code> — <reason>`.
A `429` means DeepL slowed down that shared Vercel address: wait, change the
region, or use your own DeepL Pro token.
