"""Сленг и сокращения / slang and abbreviations.

Сокращение раскрывается в полную фразу ДО перевода, поэтому падеж, род и
время получаются верными: «brb» -> «I'll be right back» -> «я скоро вернусь».
Если сервис всё же вернул латиницу, подставляется короткий русский вариант.
An abbreviation is expanded into a full phrase BEFORE translation, so case,
gender and tense come out right. If a service still returns Latin letters, a
short Russian variant is substituted.

Зачем это нужно
---------------
Живой чат пишут сокращениями: «lol», «brb», «afk», «idk». Машинный перевод
такие токены либо оставляет латиницей, либо переводит по одной букве, поэтому
в русской строке появляется мусор.

Как это работает
----------------
1. Перед переводом сокращение разворачивается в полную фразу на языке
   источника: «idk» → «I don't know», «brb» → «I'll be right back».
   Дальше обычный переводчик ставит русские слова в нужный падеж, род
   и время — «I'll be right back» → «я скоро вернусь», а не «скоро назад».
   Именно поэтому таблица хранит полную фразу, а не готовый перевод.
2. Если сервис всё же вернул сокращение как есть (так бывает с «afk», «gg»),
   его подменяет лаконичный русский вариант из второй колонки. Варианты
   подобраны так, чтобы стоять в любом месте предложения: без рода
   («не за клавиатурой», «мне всё равно»), в первом лице без прошедшего
   времени («скоро вернусь», «уже иду») или наречием («кстати», «по-моему»).
3. Обратное направление (русский → язык сервера) получает то же самое
   в русской записи: «спс» → «спасибо», «мб» → «может быть».

Свои сокращения
---------------
Встроенные таблицы дополняются тем, что игрок добавил в окне настроек
(раздел «Сокращения»). Хранятся они в data/slang.json в виде
«сокращение: [разворот, русский вариант]». Своя запись перекрывает
встроенную: так можно и переписать «afk» по-своему, и выключить ненужное
сокращение, оставив обе колонки пустыми. Если разворот пуст, а русский
вариант задан, сокращение подменяется уже после перевода.

Правки словаря безопасны: замена идёт только по целым словам и только
для известных токенов, внутри других слов («nice», «super») ничего не
меняется.
"""
import re

from app.config import SLANG_PATH, log, read_json, write_json

# сокращение: (полная фраза языка источника, лаконичный русский вариант)
FOREIGN = {
    # --- смех и междометия ---
    "lol": ("haha", "ахах"),
    "lmao": ("haha", "ахах"),
    "rofl": ("haha", "ахах"),
    "kek": ("haha", "ахах"),
    "xd": ("haha", "ахах"),
    "omg": ("oh my god", "о боже"),
    "wtf": ("what the heck", "что за чёрт"),
    "bruh": ("bro", "чувак"),
    "smh": ("shaking my head", "нет слов"),
    "ffs": ("for goodness sake", "да что ж такое"),
    # --- вежливость ---
    "ty": ("thank you", "спасибо"),
    "thx": ("thanks", "спасибо"),
    "tnx": ("thanks", "спасибо"),
    "tysm": ("thank you so much", "огромное спасибо"),
    "np": ("no problem", "не за что"),
    "yw": ("you're welcome", "не за что"),
    "pls": ("please", "пожалуйста"),
    "plz": ("please", "пожалуйста"),
    "sry": ("sorry", "извини"),
    "ily": ("I love you", "люблю тебя"),
    "kk": ("okay", "хорошо"),
    # --- уход и возвращение ---
    "brb": ("I'll be right back", "скоро вернусь"),
    "bbl": ("I'll be back later", "вернусь позже"),
    "afk": ("I'm not at the keyboard", "не за клавиатурой"),
    "omw": ("I'm on my way", "уже иду"),
    "gtg": ("I have to go", "мне пора"),
    "g2g": ("I have to go", "мне пора"),
    # --- оценка и согласие ---
    "gg": ("good game", "хорошая игра"),
    "wp": ("well played", "хорошо сыграно"),
    "ez": ("easy", "легко"),
    "gl": ("good luck", "удачи"),
    "hf": ("have fun", "хорошей игры"),
    "ofc": ("of course", "конечно"),
    "ikr": ("I know, right", "вот именно"),
    "idc": ("I don't care", "мне всё равно"),
    "idk": ("I don't know", "не знаю"),
    "nvm": ("never mind", "не важно"),
    "ngl": ("not going to lie", "врать не буду"),
    "tbh": ("to be honest", "честно говоря"),
    "imo": ("in my opinion", "по-моему"),
    "imho": ("in my humble opinion", "по-моему"),
    "btw": ("by the way", "кстати"),
    "rly": ("really", "правда"),
    "tho": ("though", "хотя"),
    # --- время и вопросы ---
    "rn": ("right now", "прямо сейчас"),
    "asap": ("as soon as possible", "как можно скорее"),
    "wdym": ("what do you mean", "что имеешь в виду"),
    "wbu": ("what about you", "а ты"),
    "hbu": ("how about you", "а ты"),
    "hru": ("how are you", "как ты"),
    "sup": ("what's up", "как дела"),
    "cya": ("see you later", "до встречи"),
    "gn": ("good night", "спокойной ночи"),
    "gm": ("good morning", "доброе утро"),
    "tmrw": ("tomorrow", "завтра"),
    "tmr": ("tomorrow", "завтра"),
    "yday": ("yesterday", "вчера"),
    # --- бытовая речь ---
    "cuz": ("because", "потому что"),
    "bc": ("because", "потому что"),
    "ppl": ("people", "люди"),
    "msg": ("message", "сообщение"),
    "u": ("you", "ты"),
    "ur": ("your", "твой"),
    # --- ролевая игра ---
    "rp": ("roleplay", "отыгрыш"),
    "ooc": ("out of character", "вне отыгрыша"),
    "ic": ("in character", "в отыгрыше"),
    # --- расширенный набор: чат, Discord, игры, RP ---
    "afaik": ("as far as I know", "насколько знаю"),
    "iirc": ("if I remember correctly", "если я правильно помню"),
    "fyi": ("for your information", "к твоему сведению"),
    "jk": ("just kidding", "шучу"),
    "tbf": ("to be fair", "если по-честному"),
    "tbfair": ("to be fair", "если по-честному"),
    "tldr": ("too long, didn't read", "если коротко"),
    "til": ("today I learned", "сегодня узнал"),
    "tmi": ("too much information", "слишком много подробностей"),
    "tfw": ("that feeling when", "когда"),
    "srsly": ("seriously", "серьёзно"),
    "prob": ("probably", "наверное"),
    "thru": ("through", "через"),
    "nw": ("no worries", "не переживай"),
    "fr": ("for real", "серьёзно"),
    "frfr": ("for real", "серьёзно"),
    "istg": ("I swear to god", "клянусь"),
    "idgaf": ("I don't give a damn", "мне всё равно"),
    "idgi": ("I don't get it", "не понимаю"),
    "idky": ("I don't know why", "не знаю почему"),
    "yolo": ("you only live once", "живём один раз"),
    "ttyl": ("talk to you later", "поговорим позже"),
    "ttys": ("talk to you soon", "скоро поговорим"),
    "tyvm": ("thank you very much", "большое спасибо"),
    "tia": ("thanks in advance", "заранее спасибо"),
    "thnx": ("thanks", "спасибо"),
    "ilysm": ("I love you so much", "очень тебя люблю"),
    "ily2": ("I love you too", "и я тебя"),
    "plox": ("please", "пожалуйста"),
    "u2": ("you too", "ты тоже"),
    "wb": ("welcome back", "с возвращением"),
    "hbd": ("happy birthday", "с днём рождения"),
    "grats": ("congratulations", "поздравляю"),
    "gz": ("congratulations", "поздравляю"),
    "l8r": ("later", "позже"),
    "cu": ("see you", "увидимся"),
    "cul8r": ("see you later", "до встречи"),
    "bbs": ("be back soon", "скоро вернусь"),
    "brt": ("be right there", "уже там"),
    "eta": ("estimated time of arrival", "когда будешь"),
    "w8": ("wait", "подожди"),
    "wknd": ("weekend", "выходные"),
    "2moro": ("tomorrow", "завтра"),
    "2nite": ("tonight", "сегодня вечером"),
    "l8": ("late", "поздно"),
    "gr8": ("great", "отлично"),
    "m8": ("mate", "друг"),
    "b4": ("before", "до"),
    "4u": ("for you", "для тебя"),
    "n/a": ("not available", "нет данных"),
    "w/o": ("without", "без"),
    "b/c": ("because", "потому что"),
    "wdyt": ("what do you think", "что думаешь"),
    "wym": ("what you mean", "что имеешь в виду"),
    "wby": ("what about you", "а ты"),
    "wru": ("where are you", "ты где"),
    "hmu": ("hit me up", "напиши мне"),
    "lmk": ("let me know", "дай знать"),
    "smn": ("someone", "кто-нибудь"),
    "sth": ("something", "что-то"),
    "smt": ("something", "что-то"),
    "irl": ("in real life", "в реальной жизни"),
    "rl": ("real life", "реальная жизнь"),
    "iow": ("in other words", "другими словами"),
    "nsfw": ("not safe for work", "не для работы"),
    "wfh": ("working from home", "работаю из дома"),
    "tgif": ("thank god it's Friday", "наконец пятница"),
    "rt": ("repost", "репост"),
    "yt": ("YouTube", "Ютуб"),
    "tg": ("Telegram", "телеграм"),
    "vk": ("VKontakte", "вконтакте"),
    "dm": ("direct message", "личное сообщение"),
    "pm": ("private message", "личное сообщение"),
    "omfg": ("oh my god", "о боже"),
    "wth": ("what the hell", "что за чёрт"),
    "tf": ("what the heck", "что за чёрт"),
    "zzz": ("sleeping", "сплю"),
    "o7": ("salute", "честь"),
    "ggs": ("good games", "хорошие игры"),
    "ggez": ("good game, easy", "лёгкая победа"),
    "ezpz": ("easy", "легко"),
    "glhf": ("good luck, have fun", "удачи и хорошей игры"),
    "nt": ("nice try", "хорошая попытка"),
    "gj": ("good job", "молодец"),
    "op": ("overpowered", "слишком сильный"),
    "pvp": ("player versus player", "бой игрок против игрока"),
    "pve": ("player versus environment", "игра против компьютера"),
    "npc": ("non-player character", "неигровой персонаж"),
    "mmo": ("massively multiplayer online game", "массовая онлайн-игра"),
    "dps": ("damage per second", "урон в секунду"),
    "xp": ("experience", "опыт"),
    "lvl": ("level", "уровень"),
    "ult": ("ultimate ability", "ульта"),
    "aoe": ("area of effect", "по площади"),
    "dc": ("disconnected", "отключился"),
    "kb": ("keyboard", "клавиатура"),
    "acc": ("account", "аккаунт"),
    "inv": ("inventory", "инвентарь"),
    "srv": ("server", "сервер"),
    "vc": ("voice chat", "голосовой чат"),
    "mic": ("microphone", "микрофон"),
    "cam": ("camera", "камера"),
    "wtb": ("want to buy", "хочу купить"),
    "wts": ("want to sell", "хочу продать"),
    "wtt": ("want to trade", "хочу обменять"),
    "ff": ("forfeit", "сдаться"),
    "og": ("original", "старожил"),
    "em": ("emote", "эмоция"),
    "para": ("paragraph", "абзац"),
}

# растянутый смех: «looool», «lmaoo», «rofl», «xD», «kek»
LAUGH = ((r"l+o+l+", "haha", "ахах"),
         (r"lma+o+", "haha", "ахах"),
         (r"rofl+", "haha", "ахах"),
         (r"x+d+", "haha", "ахах"),
         (r"ke+k+", "haha", "ахах"))

# русские сокращения → полная запись (для направления «русский → язык»)
RUSSIAN = {
    "спс": "спасибо",
    "спсб": "спасибо",
    "сенкс": "спасибо",
    "пж": "пожалуйста",
    "пож": "пожалуйста",
    "нзч": "не за что",
    "нз": "не знаю",
    "хз": "не знаю",
    "мб": "может быть",
    "крч": "короче",
    "ща": "сейчас",
    "оч": "очень",
    "тож": "тоже",
    "збс": "отлично",
    "норм": "нормально",
    "прив": "привет",
    "спок": "спокойной ночи",
    "инфа": "информация",
    "имхо": "по-моему",
    "бтв": "кстати",
    "чё": "что",
    "щас": "сейчас",
    "ваще": "вообще",
    "плз": "пожалуйста",
    "благ": "благодарю",
    "пок": "пока",
    "чел": "человек",
    "инет": "интернет",
    "комп": "компьютер",
    "тел": "телефон",
    "др": "день рождения",
}

CYR_RX = re.compile(r"[а-яё]", re.IGNORECASE)


def is_russian_token(token):
    """Сокращение записано кириллицей — значит, оно русское."""
    return bool(CYR_RX.search(str(token or "")))


# ---------- рабочие таблицы (встроенные + то, что добавил игрок) ----------
_user = {}                 # сокращение -> (разворот, русский вариант)
_foreign = dict(FOREIGN)
_russian = dict(RUSSIAN)
_loaded = False

_RX_FOREIGN = None
_RX_RUSSIAN = None


def _token_rx(words):
    """Регулярка по целым словам: длинные варианты идут первыми."""
    if not words:
        return None
    parts = sorted(words, key=len, reverse=True)
    return re.compile(r"(?<![0-9A-Za-z_а-яёА-ЯЁ])(?:%s)(?![0-9A-Za-z_а-яёА-ЯЁ])"
                      % "|".join(re.escape(p) for p in parts), re.IGNORECASE)


_RX_LAUGH = re.compile(r"(?<![0-9A-Za-z_])(?:%s)(?![0-9A-Za-z_])"
                       % "|".join(p for p, _en, _ru in LAUGH), re.IGNORECASE)

# «I'm afk» → «I'm not at the keyboard», а не «I'm I'm away…»:
# если перед сокращением уже стоит подлежащее или форма to be, берём вариант
# без ведущего «I»/«I'm»/«I'll».
_LEAD_RX = re.compile(r"^(?:i'm|i am|i'll|i've|i)\s+", re.IGNORECASE)
_SUBJECT_RX = re.compile(
    r"(?:\b(?:i'm|im|i am|i'll|i've|he's|she's|it's|we're|they're|you're|"
    r"is|are|am|was|were)\s*,?\s*"
    r"(?:(?:not|never|still|really|always|so|just|probably|already)\s+){0,2})$",
    re.IGNORECASE)


def _tail_form(english):
    """Полная фраза без ведущего «I»/«I'm»/«I'll» — для контекста с подлежащим."""
    return _LEAD_RX.sub("", english)


def _has_subject(text, pos):
    """Есть ли прямо перед сокращением подлежащее или форма to be."""
    return bool(_SUBJECT_RX.search(text[:pos]))


_TAILS = {}


def _rebuild():
    """Пересобирает рабочие таблицы и регулярки под текущий набор сокращений."""
    global _foreign, _russian, _RX_FOREIGN, _RX_RUSSIAN, _TAILS
    _foreign = dict(FOREIGN)
    _russian = dict(RUSSIAN)
    for token, pair in _user.items():
        expand, ru = (list(pair) + ["", ""])[:2]
        expand, ru = str(expand or "").strip(), str(ru or "").strip()
        if is_russian_token(token):
            if expand or ru:
                _russian[token] = expand or ru
            else:
                _russian.pop(token, None)
        elif expand or ru:
            _foreign[token] = (expand, ru)
        else:
            _foreign.pop(token, None)
    _RX_FOREIGN = _token_rx(_foreign)
    _RX_RUSSIAN = _token_rx(_russian)
    _TAILS = {token: _tail_form(item[0]) for token, item in _foreign.items() if item[0]}


# ---------- свои сокращения игрока ----------
def load_user():
    """Читает data/slang.json (если он есть) и применяет к таблицам."""
    global _loaded
    data = read_json(SLANG_PATH, {})
    entries = data.get("custom") if isinstance(data, dict) and "custom" in data else data
    _set_user(entries if isinstance(entries, dict) else {})
    _loaded = True
    return dict(_user)


def _set_user(entries):
    global _user
    clean = {}
    for token, pair in (entries or {}).items():
        token = str(token or "").strip()
        if not token:
            continue
        if isinstance(pair, dict):
            pair = [pair.get("expand", ""), pair.get("ru", "")]
        elif isinstance(pair, str):
            pair = [pair, ""]
        pair = list(pair) + ["", ""]
        clean[token] = (str(pair[0] or "").strip(), str(pair[1] or "").strip())
    _user = clean
    _rebuild()


def set_user(entries):
    """Применить свои сокращения только в памяти (без записи на диск)."""
    _set_user(entries)
    return dict(_user)


def user_entries():
    """То, что добавлено игроком: сокращение -> [разворот, русский вариант]."""
    return {k: [v[0], v[1]] for k, v in _user.items()}


def save_user(entries):
    """Записать свои сокращения в data/slang.json и применить их."""
    _set_user(entries)
    try:
        write_json(SLANG_PATH, {"custom": user_entries()})
    except OSError:
        log.exception("Не удалось сохранить свои сокращения")
    log.info("Своих сокращений сохранено: %d", len(_user))
    return dict(_user)


def entries():
    """Полная таблица для окна настроек: [(сокращение, разворот, вариант, своё?)].

    Своё показано как «своё», встроенное — как «встроенное»; выключенное
    сокращение (обе колонки пусты) остаётся в списке, чтобы его можно было
    вернуть.
    """
    rows = []
    for token, (expand, ru) in _foreign.items():
        rows.append((token, expand, ru, token in _user))
    for token, expand in _russian.items():
        rows.append((token, expand, "", token in _user))
    for token in _user:
        if token not in _foreign and token not in _russian:
            rows.append((token, "", "", True))       # выключенное сокращение
    rows.sort(key=lambda r: (not r[3], r[0].lower()))
    return rows


def known():
    """Сколько сокращений в таблицах — для справки и самопроверки."""
    return {"иностранные": len(_foreign) + len(LAUGH), "русские": len(_russian),
            "свои": len(_user)}


def _ensure():
    if not _loaded:
        load_user()


# ---------- замена ----------
def _capitalize(word):
    return word[:1].upper() + word[1:]


def _at_sentence_start(text, pos):
    """True, если перед позицией конец строки или знак конца предложения."""
    before = text[:pos].rstrip()
    return (not before) or before[-1] in ".!?…;:—-*\"«("


def _replace(text, rx, pick):
    """Общая замена по регулярке; pick(токен, начало) -> строка или None."""
    if rx is None:
        return text, []
    out, pos, hits = [], 0, []
    for m in rx.finditer(text):
        token = m.group(0)
        new = pick(token, m.start())
        if new is None:
            continue
        out.append(text[pos:m.start()])
        out.append(new)
        pos = m.end()
        hits.append((token, new))
    if not hits:
        return text, hits
    out.append(text[pos:])
    return "".join(out), hits


def expand_foreign(text):
    """Сокращение → полная фраза перед переводом. Возвращает (текст, замены)."""
    if not text:
        return text, []
    _ensure()
    hits = []

    def by_laugh(token, start):
        lower = token.lower()
        for pattern, en, _ru in LAUGH:
            if re.fullmatch(pattern, lower):
                return en
        return None

    text, more = _replace(text, _RX_LAUGH, by_laugh)
    hits += more

    def by_token(token, start):
        lower = token.lower()
        item = _foreign.get(lower)
        if not item or not item[0]:
            return None
        tail = _TAILS.get(lower)
        if tail and _has_subject(text, start):
            return tail
        return item[0]

    text, more = _replace(text, _RX_FOREIGN, by_token)
    return text, hits + more


def restore_russian(text):
    """Оставшиеся латинские сокращения → лаконичный русский вариант."""
    if not text:
        return text, []
    _ensure()

    def pick(token, start):
        item = _foreign.get(token.lower())
        if not item or not item[1]:
            return None
        ru = item[1]
        return _capitalize(ru) if _at_sentence_start(text, start) else ru

    return _replace(text, _RX_FOREIGN, pick)


def expand_russian(text):
    """Русское сокращение → полная русская запись (перед переводом на язык)."""
    if not text:
        return text, []
    _ensure()

    def pick(token, start):
        word = _russian.get(token.lower())
        if not word:
            return None
        return _capitalize(word) if _at_sentence_start(text, start) else word

    return _replace(text, _RX_RUSSIAN, pick)
