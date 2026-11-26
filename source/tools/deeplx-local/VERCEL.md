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
- Node.js 22.x на компьютере — чтобы запускать тесты и, при желании, пользоваться
  Vercel CLI; версия Node для production-деплоя зафиксирована в `package.json`;
- ничего платить не надо: тариф Hobby бесплатный и подходит для личных проектов.

Что именно заливать: **содержимое папки `source/tools/deeplx-local`**, а не весь
проект. В ней уже лежит всё нужное:

```text
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
   - **Environment Variables** — добавьте `TOKEN` для Production до первого деплоя.
     Сгенерировать случайный токен можно командой Node.js:
     `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`.
     Сохраните значение в менеджере паролей: повторно увидеть его в Vercel нельзя.
4. **Deploy**. Сборка занимает меньше минуты.

Готово: Vercel покажет адрес `https://имя-проекта.vercel.app`. Не публикуйте
адрес и токен вместе; сам токен используйте только в поле авторизации.

> Если вы залили в репозиторий **весь проект** (а не только папку), то в
> **Settings → General → Root Directory** укажите
> `source/tools/deeplx-local` и нажмите **Redeploy**.

### 3. Проверить, что работает

Проверьте health-ответ в браузере:

```text
https://имя-проекта.vercel.app/api/
```

Должен вернуться JSON со `code: 200` и сообщением `DeepLX on Vercel is running`.
Это проверяет доступность функции, но не сам DeepL-перевод.

Проверка перевода в PowerShell. Замените адрес на **полный URL своего проекта**
(из Vercel, начиная с `https://`) и введите точное значение `TOKEN`, сохранённое
в Vercel. Выполните блок целиком — если пропустить `$base`, PowerShell не сможет
разобрать адрес; пустой токен не пройдёт авторизацию:

```powershell
$base = 'https://your-project.vercel.app' # замените на домен из Vercel
$token = 'paste-the-TOKEN-you-saved-in-Vercel-here'

if ($base -notmatch '^https://[^/]+$' -or $base -eq 'https://your-project.vercel.app') {
  throw 'Замените пример на базовый HTTPS-адрес проекта из Vercel.'
}
if ([string]::IsNullOrWhiteSpace($token) -or $token -eq 'paste-the-TOKEN-you-saved-in-Vercel-here') {
  throw 'Вставьте точное значение TOKEN из Vercel.'
}

$uri = "$($base.TrimEnd('/'))/api/translate"
$headers = @{ Authorization = "Bearer $token" }
$json = @{
  text = 'Привет, как дела?'
  source_lang = 'RU'
  target_lang = 'IT'
} | ConvertTo-Json -Compress
# Явно кодируем JSON в UTF-8: это важно для Windows PowerShell 5.1 и кириллицы.
$body = [System.Text.Encoding]::UTF8.GetBytes($json)

# Убедитесь, что в JSON до отправки указаны RU и IT.
$json
$request = @{
  Method = 'Post'
  Uri = $uri
  Headers = $headers
  ContentType = 'application/json; charset=utf-8'
  Body = $body
}
$response = Invoke-RestMethod @request
$response | Format-List code, source_lang, target_lang, data, message
```

В ответе ожидается `code: 200` и непустое поле `data`. Для macOS/Linux:

```bash
curl -sS "$BASE/api/translate" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"text":"Привет, как дела?","source_lang":"RU","target_lang":"IT"}'
```

Если запрос без токена получает `401`, защита включена. `GET` health-маршруты
публичны и не проверяют авторизацию; именно POST-тест подтверждает защиту и
работу перевода.

### Если сервис уже развернули без токена

Считайте адрес открытым до передеплоя. В Vercel откройте **Settings → Environment
Variables**, добавьте `TOKEN` для Production, сохраните, затем выполните
**Deployments → ⋯ у последнего production-деплоя → Redeploy**. После этого
повторите POST-проверку выше с токеном и убедитесь, что POST без него возвращает
`401`. Если старый токен мог попасть в историю/логи, замените его новым и снова
передеплойте.

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

```text
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
  Сервис пишет структурированные события и HTTP-коды, не включая текст перевода
  или исходный ответ DeepL.
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
2. Vercel → **Add New → Project** → import the repo → **Framework Preset: Other**,
   build command empty, root directory `./` (or `source/tools/deeplx-local` if
   you pushed the whole project). Set a random `TOKEN` in the import form before
   the first Production deployment, then deploy. Pin Node to `22.x` (already
   declared in `package.json`).
3. Open `https://your-project.vercel.app/api/` in a browser: expect HTTP 200 and
   a JSON health message. Test POST `/api/translate` with `Authorization:
   Bearer <TOKEN>`; POST without the token must return 401. See the PowerShell and
   curl examples above.
4. If the project is already deployed without `TOKEN`, add it in **Settings →
   Environment Variables** and immediately **Redeploy**. Until that finishes,
   translation requests are public.
5. In the program: **Settings → DeepL → "Your own service address"** =
   `https://your-project.vercel.app`, **"Your own service token"** = the same
   `TOKEN`. Save. No `dlx.exe` needed any more.

Hobby plan: 30 s function limit (set in `vercel.json`), 100 GB bandwidth a month,
personal projects only. Pick the Frankfurt region for a shorter path to DeepL.
Structured failure events and HTTP codes appear in Vercel → Logs; translation
text and raw DeepL responses are not logged. A `429` means DeepL slowed down that
shared Vercel address: wait, change the region, or use your own DeepL Pro token.
