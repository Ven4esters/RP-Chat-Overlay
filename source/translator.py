"""translator.py — перевод ru → язык и язык → ru.

Направления:
    "out" (по умолчанию): русский текст → выбранный язык перевода;
    "in"  (режим переводчика): любой язык (определяется автоматически) → русский.

Сервисы идут цепочкой, пока один не ответит:
    Google gtx → Google clients5 → Google web (deep-translator) → MyMemory →
    Lingva (несколько зеркал) → LibreTranslate (несколько зеркал).
Если сервис ответил «429 / too many requests», он временно исключается из
цепочки (COOL секунд), чтобы не тратить время на заведомо занятый сервис.
MyMemory и LibreTranslate не умеют автоопределение языка — в режиме "in"
они пропускаются, поэтому там работают Google (два эндпоинта) и Lingva.
"""
import html
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from common import CACHE_PATH, log, read_json, write_json
from langs import code_of, get as get_lang

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MIN_GAP = 0.35      # секунд между сетевыми запросами
TIMEOUT = 4         # секунд на запрос
DEADLINE = 16       # секунд на всю цепочку — дольше ждать бессмысленно
COOL = 120          # секунд, на которые занятый сервис выпадает из цепочки
CACHE_MAX = 2000
RU = "ru"
IN_ALIASES = ("in", "reverse", "to_ru", "tо_ru", "ru")

# зеркала Lingva и LibreTranslate: публичные инстансы живут нестабильно,
# поэтому идём по списку, а не по одному адресу
LINGVA_HOSTS = ("https://lingva.ml", "https://lingva.garudalinux.org",
                "https://translate.plausibility.cloud")
LIBRE_HOSTS = ("https://libretranslate.de", "https://translate.terraprint.co",
               "https://trans.zillyhuhn.com")

_cool = {}          # имя сервиса -> до какого времени (time.time()) не пробовать
_cool_lock = threading.Lock()


class TranslateError(Exception):
    pass


def _http_json(url, data=None):
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_text(url, data=None):
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def _is_busy(err):
    """Сервис ответил «слишком много запросов» — его стоит остудить."""
    text = str(err).lower()
    return ("429" in text or "too many" in text or "rate limit" in text
            or "quota" in text)


# ---------------------------------------------------------------- Google
def _google_gtx(text, target, source="ru"):
    q = urllib.parse.urlencode(
        {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    )
    data = _http_json("https://translate.googleapis.com/translate_a/single?" + q)
    return "".join(p[0] for p in data[0] if p and p[0])


def _google_clients5(text, target, source="ru"):
    """Второй эндпоинт Google: своя квота, поэтому живёт, когда gtx отдаёт 429."""
    q = urllib.parse.urlencode(
        {"client": "dict-chrome-ex", "sl": source, "tl": target, "q": text}
    )
    data = _http_json("https://clients5.google.com/translate_a/t?" + q)
    if isinstance(data, list):
        if data and isinstance(data[0], list):        # [[«Привет, мир», «en»]]
            return str(data[0][0] or "")
        if data and isinstance(data[0], str):         # ["Ciao"]
            return data[0]
        if data and isinstance(data[0], dict):        # {"sentences": [...]}
            return "".join(s.get("trans", "") for s in data[0].get("sentences") or [])
    if isinstance(data, dict):
        return str(data.get("translation") or data.get("trans") or "")
    return ""


def _google_web(text, target, source="ru"):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=source, target=target).translate(text)


# ---------------------------------------------------------------- Lingva
def _lingva(text, target, source="ru"):
    """Lingva (открытая альтернатива Google): умеет автоопределение языка."""
    last = None
    for host in LINGVA_HOSTS:
        try:
            url = "%s/api/v1/%s/%s/%s" % (host, source or "auto", target,
                                          urllib.parse.quote(text, safe=""))
            data = _http_json(url)
            res = (data.get("translation") or "").strip()
            if res:
                return res
            last = RuntimeError("пустой ответ %s" % host)
        except Exception as e:                        # зеркало могло умереть
            last = e
    raise last or RuntimeError("Lingva недоступна")


# ---------------------------------------------------------------- Libre
def _free_libre(text, target, source="ru"):
    """LibreTranslate: без auto, поэтому в режиме «язык → русский» пропускается."""
    if source == "auto":
        raise RuntimeError("LibreTranslate не поддерживает автоопределение")
    last = None
    payload = urllib.parse.urlencode(
        {"q": text, "source": source, "target": target, "format": "text"}
    ).encode()
    for host in LIBRE_HOSTS:
        try:
            raw = _http_text(host.rstrip("/") + "/translate", data=payload)
            data = json.loads(raw)
            res = (data.get("translatedText") or "").strip()
            if res:
                return res
            last = RuntimeError("пустой ответ %s" % host)
        except Exception as e:
            last = e
    raise last or RuntimeError("LibreTranslate недоступна")


# ---------------------------------------------------------------- MyMemory
def _mymemory(text, target, source="ru"):
    if source == "auto":
        # MyMemory требует конкретный код языка — в режиме автоопределения пропускаем
        raise RuntimeError("MyMemory не поддерживает автоопределение языка")
    q = urllib.parse.urlencode({"q": text, "langpair": source + "|" + target})
    data = _http_json("https://api.mymemory.translated.net/get?" + q)
    res = (data.get("responseData") or {}).get("translatedText") or ""
    if str(data.get("responseStatus")) != "200" or "MYMEMORY WARNING" in res.upper():
        raise RuntimeError(res or data.get("responseDetails") or "нет ответа")
    return html.unescape(res)


# Порядок важен: сначала то, что отвечает быстро и умеет автоопределение.
SERVICES = (
    ("Google", _google_gtx),
    ("Google-2", _google_clients5),
    ("Google-web", _google_web),
    ("MyMemory", _mymemory),
    ("Lingva", _lingva),
    ("LibreTranslate", _free_libre),
)


def _short(errors):
    """Короткое объяснение для окна: что именно случилось со всеми сервисами."""
    text = " ".join(errors).lower()
    if "429" in text or "too many" in text or "quota" in text:
        return "сервисы заняты, Google ограничил запросы (429)"
    if ("urlopen error" in text or "timed out" in text or "getaddrinfo" in text
            or "connection" in text):
        return "нет соединения с сервисами перевода"
    return "сервисы не ответили"


class Translator:
    """Перевод в выбранном направлении. Кэш общий, но с направлением и языком в ключе."""

    def __init__(self, target="it"):
        cache = read_json(CACHE_PATH, {})
        self.cache = cache if isinstance(cache, dict) else {}
        self.net_lock = threading.Lock()
        self.last = 0.0
        self.out_target = "it"        # выбранный язык перевода (для направления "out")
        self.direction = "out"        # "out" | "in"
        self.target = "it"
        self.source = "ru"
        self.last_service = ""        # чем перевели в последний раз — для журнала
        self.set_target(target)

    # ----- режим -----
    @staticmethod
    def is_reverse(direction):
        """True, если направление — «ваш язык → русский»."""
        return str(direction).strip().lower() in IN_ALIASES

    def set_direction(self, direction):
        """Переключить направление перевода: "out" (ru → язык) или "in" (язык → ru)."""
        self.direction = "in" if self.is_reverse(direction) else "out"
        if self.direction == "in":
            self.target, self.source = RU, "auto"
        else:
            self.target = get_lang(code_of(self.out_target))["tr"]
            self.source = "ru"
        log.info("Направление перевода: %s -> %s", self.source, self.target)
        return self.direction

    def set_target(self, target):
        """Сменить язык перевода (код из langs.py). В режиме "in" запоминается."""
        self.out_target = target
        if self.direction != "in":
            code = get_lang(code_of(target))["tr"]
            if code != self.target:
                self.target = code
                log.info("Язык перевода: %s", code)
        else:
            self.set_direction("in")
        return self.target

    # ----- сервисы -----
    @staticmethod
    def _available(name, now):
        with _cool_lock:
            return _cool.get(name, 0) <= now

    @staticmethod
    def _cool_down(name, now):
        with _cool_lock:
            _cool[name] = now + COOL

    # ----- перевод -----
    def translate(self, text):
        key = text.strip()
        if not key:
            return ""
        ck = ("in\x1f" if self.direction == "in" else "out\x1f") + self.target + "\x1f" + key
        if ck in self.cache:
            return self.cache[ck]
        errors = []
        target, source = self.target, self.source
        started = time.time()
        with self.net_lock:                      # запросы строго по одному
            if ck in self.cache:
                return self.cache[ck]
            for name, func in SERVICES:
                now = time.time()
                if now - started > DEADLINE:
                    errors.append("время ожидания истекло")
                    break
                if not self._available(name, now):
                    errors.append(f"{name}: недавно был занят")
                    continue
                wait = MIN_GAP - (now - self.last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    res = (func(key, target, source) or "").strip()
                    self.last = time.time()
                    if res:
                        self._store(ck, res)
                        self.last_service = name
                        log.info("Перевод через %s (%s->%s): %r -> %r",
                                 name, source, target, key, res)
                        return res
                    errors.append(f"{name}: пустой ответ")
                except Exception as e:
                    now = time.time()
                    self.last = now
                    errors.append(f"{name}: {str(e)[:70]}")
                    if _is_busy(e):
                        self._cool_down(name, now)
        log.warning("Перевод не удался: %s", "; ".join(errors))
        raise TranslateError(_short(errors) + " (" + "; ".join(errors)[:160] + ")")

    def _store(self, key, value):
        self.cache[key] = value
        while len(self.cache) > CACHE_MAX:
            self.cache.pop(next(iter(self.cache)))
        try:
            write_json(CACHE_PATH, self.cache)
        except OSError:
            log.exception("Не удалось сохранить кэш")
