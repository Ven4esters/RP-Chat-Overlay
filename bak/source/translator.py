"""translator.py — машинный перевод ru → выбранный язык: Google gtx → deep-translator → MyMemory."""
import html
import json
import threading
import time
import urllib.parse
import urllib.request

from common import CACHE_PATH, log, read_json, write_json
from langs import code_of, get as get_lang

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MIN_GAP = 0.4      # секунд между сетевыми запросами
TIMEOUT = 6        # секунд на запрос
CACHE_MAX = 2000


class TranslateError(Exception):
    pass


def _http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _google_gtx(text, target):
    q = urllib.parse.urlencode(
        {"client": "gtx", "sl": "ru", "tl": target, "dt": "t", "q": text}
    )
    data = _http_json("https://translate.googleapis.com/translate_a/single?" + q)
    return "".join(p[0] for p in data[0] if p and p[0])


def _google_web(text, target):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="ru", target=target).translate(text)


def _mymemory(text, target):
    q = urllib.parse.urlencode({"q": text, "langpair": "ru|" + target})
    data = _http_json("https://api.mymemory.translated.net/get?" + q)
    res = (data.get("responseData") or {}).get("translatedText") or ""
    if str(data.get("responseStatus")) != "200" or "MYMEMORY WARNING" in res.upper():
        raise RuntimeError(res or data.get("responseDetails") or "нет ответа")
    return html.unescape(res)


SERVICES = (
    ("Google", _google_gtx),
    ("Google-web", _google_web),
    ("MyMemory", _mymemory),
)


class Translator:
    """Перевод с русского на язык self.target. Кэш общий, но с языком в ключе."""

    def __init__(self, target="it"):
        cache = read_json(CACHE_PATH, {})
        self.cache = cache if isinstance(cache, dict) else {}
        self.net_lock = threading.Lock()
        self.last = 0.0
        self.target = "it"
        self.set_target(target)

    def set_target(self, target):
        """Сменить язык перевода (код из langs.py)."""
        code = get_lang(code_of(target))["tr"]
        if code != self.target:
            self.target = code
            log.info("Язык перевода: %s", code)
        return self.target

    def translate(self, text):
        key = text.strip()
        if not key:
            return ""
        ck = self.target + "\x1f" + key
        if ck in self.cache:
            return self.cache[ck]
        errors = []
        target = self.target
        with self.net_lock:                      # запросы строго по одному
            if ck in self.cache:
                return self.cache[ck]
            for name, func in SERVICES:
                wait = MIN_GAP - (time.time() - self.last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    res = (func(key, target) or "").strip()
                    self.last = time.time()
                    if res:
                        self._store(ck, res)
                        log.info("Перевод через %s (%s): %r -> %r", name, target, key, res)
                        return res
                    errors.append(f"{name}: пустой ответ")
                except Exception as e:
                    self.last = time.time()
                    errors.append(f"{name}: {str(e)[:70]}")
        log.warning("Перевод не удался: %s", "; ".join(errors))
        raise TranslateError("; ".join(errors))

    def _store(self, key, value):
        self.cache[key] = value
        while len(self.cache) > CACHE_MAX:
            self.cache.pop(next(iter(self.cache)))
        try:
            write_json(CACHE_PATH, self.cache)
        except OSError:
            log.exception("Не удалось сохранить кэш")
