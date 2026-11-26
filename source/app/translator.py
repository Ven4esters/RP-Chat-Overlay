"""Перевод по сети: русский → выбранный язык и любой язык → русский.

Online translation: Russian into the chosen language and any language into Russian.

Направления / directions
------------------------
    "out" (по умолчанию / default) — русский текст → язык перевода;
    "in"  (режим переводчика)      — любой язык (определяется сам) → русский.

Цепочка сервисов / the service chain
------------------------------------
    Google gtx → Google clients5 → Google web → MyMemory → Lingva → LibreTranslate
Первый ответивший выигрывает, остальные не трогаются. Если сервис ответил
«429 / too many requests», он выпадает из цепочки на COOL секунд, чтобы не
тратить время на заведомо занятый адрес.
The first service that answers wins. A service that answers "429 / too many
requests" leaves the chain for COOL seconds, so a busy endpoint is not retried
on every keystroke.

Ограничения сервисов / service limits
-------------------------------------
MyMemory и LibreTranslate не умеют определять язык сами, поэтому в режиме "in"
они пропускаются: там работают два адреса Google и Lingva.
MyMemory and LibreTranslate cannot detect the language, so they are skipped in
the "in" direction, where the two Google endpoints and Lingva do the work.
"""

from __future__ import annotations

from contextlib import contextmanager
import calendar
from datetime import datetime, timedelta, timezone
import html
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Final

from app.config import CACHE_PATH, log, read_json, write_json
from app.langs import code_of, get as get_lang
from app.usage_report import measure_call

# --------------------------------------------------------------- настройки сети
UA: dict[str, str] = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MIN_GAP = 0.35  # секунд между сетевыми запросами / seconds between requests
TIMEOUT = 4  # секунд на один запрос / seconds per request
DEADLINE = 16  # секунд на всю цепочку / seconds for the whole chain
COOL = 120  # секунд «отдыха» занятого сервиса / cooldown for a busy service
CACHE_MAX = 2000  # сколько переводов помнить / cached translations kept
CACHE_SAVE_EVERY = 2.0  # как часто писать кэш на диск / how often to persist
RU = "ru"
IN_ALIASES = ("in", "reverse", "to_ru", "tо_ru", "ru")

# Публичные зеркала живут нестабильно, поэтому идём по списку адресов,
# а не по одному. Public mirrors are unstable, so a list is tried in order.
LINGVA_HOSTS = (
    "https://lingva.ml",
    "https://lingva.garudalinux.org",
    "https://translate.plausibility.cloud",
)
LIBRE_HOSTS = (
    "https://libretranslate.de",
    "https://translate.terraprint.co",
    "https://trans.zillyhuhn.com",
)

_cool: dict[str, float] = {}  # сервис -> до какого времени не пробовать
_cool_lock = threading.Lock()

ServiceFunc = Callable[[str, str, str], str]


class TranslateError(Exception):
    """Перевод не удался: сеть, занятые сервисы или все адреса молчат.

    Translation failed: no network, busy services, or every address is silent.
    """


# ------------------------------------------------------------------- HTTP
_request_context = threading.local()


@contextmanager
def _request_deadline_scope(deadline: float):
    """Bound each HTTP request by the remaining time in the whole chain."""
    previous = getattr(_request_context, "deadline", None)
    _request_context.deadline = deadline
    try:
        yield
    finally:
        if previous is None:
            del _request_context.deadline
        else:
            _request_context.deadline = previous


def _request_timeout() -> float:
    deadline = getattr(_request_context, "deadline", None)
    if deadline is None:
        return TIMEOUT
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("translation deadline exceeded")
    return min(TIMEOUT, remaining)


def _http_json(url: str, data: bytes | None = None) -> Any:
    """GET/POST с разбором JSON / request that returns parsed JSON."""
    request = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(request, timeout=_request_timeout()) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_text(url: str, data: bytes | None = None) -> str:
    """GET/POST, ответ как текст / request that returns raw text."""
    request = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(request, timeout=_request_timeout()) as response:
        return response.read().decode("utf-8", "replace")


def _is_busy(error: Exception) -> bool:
    """Сервис ответил «слишком много запросов» — его стоит остудить.

    True when the service answered "too many requests" and deserves a cooldown.
    """
    text = str(error).lower()
    return "429" in text or "too many" in text or "rate limit" in text or "quota" in text


# ------------------------------------------------------------------ Google
def _google_gtx(text: str, target: str, source: str = RU) -> str:
    """Основной адрес Google / the primary Google endpoint."""
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    )
    data = _http_json("https://translate.googleapis.com/translate_a/single?" + query)
    return "".join(part[0] for part in data[0] if part and part[0])


def _google_clients5(text: str, target: str, source: str = RU) -> str:
    """Второй адрес Google: своя квота, поэтому живёт, когда gtx отдаёт 429.

    The second Google endpoint. It has its own quota, so it still answers while
    gtx returns 429. The response shape varies: [[text, lang]], ["text"] or
    [{"sentences": [...]}].
    """
    query = urllib.parse.urlencode(
        {"client": "dict-chrome-ex", "sl": source, "tl": target, "q": text}
    )
    data = _http_json("https://clients5.google.com/translate_a/t?" + query)
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return str(data[0][0] or "")
        if data and isinstance(data[0], str):
            return data[0]
        if data and isinstance(data[0], dict):
            return "".join(sentence.get("trans", "") for sentence in data[0].get("sentences") or [])
    if isinstance(data, dict):
        return str(data.get("translation") or data.get("trans") or "")
    return ""


# ------------------------------------------------------------------- Lingva
def _lingva(text: str, target: str, source: str = RU) -> str:
    """Lingva (открытая альтернатива Google): умеет автоопределение языка.

    Lingva, an open Google alternative that can detect the language itself.
    """
    last: Exception | None = None
    for host in LINGVA_HOSTS:
        try:
            url = "%s/api/v1/%s/%s/%s" % (
                host,
                source or "auto",
                target,
                urllib.parse.quote(text, safe=""),
            )
            data = _http_json(url)
            result = (data.get("translation") or "").strip()
            if result:
                return result
            last = RuntimeError("пустой ответ %s" % host)
        except Exception as error:  # зеркало могло умереть / mirror is down
            last = error
    raise last or RuntimeError("Lingva недоступна")


# ------------------------------------------------------------- LibreTranslate
def _free_libre(text: str, target: str, source: str = RU) -> str:
    """LibreTranslate: без автоопределения, в режиме «язык → русский» пропускается.

    LibreTranslate cannot detect the language, so it is skipped when the source
    language is unknown.
    """
    if source == "auto":
        raise RuntimeError("LibreTranslate не поддерживает автоопределение")
    last: Exception | None = None
    payload = urllib.parse.urlencode(
        {"q": text, "source": source, "target": target, "format": "text"}
    ).encode()
    for host in LIBRE_HOSTS:
        try:
            raw = _http_text(host.rstrip("/") + "/translate", data=payload)
            data = json.loads(raw)
            result = (data.get("translatedText") or "").strip()
            if result:
                return result
            last = RuntimeError("пустой ответ %s" % host)
        except Exception as error:
            last = error
    raise last or RuntimeError("LibreTranslate недоступна")


# ----------------------------------------------------------------- MyMemory
def _mymemory(text: str, target: str, source: str = RU) -> str:
    """MyMemory: требует точный код языка / MyMemory needs an explicit language."""
    if source == "auto":
        raise RuntimeError("MyMemory не поддерживает автоопределение языка")
    query = urllib.parse.urlencode({"q": text, "langpair": source + "|" + target})
    data = _http_json("https://api.mymemory.translated.net/get?" + query)
    result = (data.get("responseData") or {}).get("translatedText") or ""
    if str(data.get("responseStatus")) != "200" or "MYMEMORY WARNING" in result.upper():
        raise RuntimeError(result or data.get("responseDetails") or "нет ответа")
    return html.unescape(result)


# Порядок важен: сначала то, что отвечает быстро и умеет автоопределение.
# The order matters: fast services that detect the language go first.
SERVICES: tuple[tuple[str, ServiceFunc], ...] = (
    ("Google", _google_gtx),
    ("Google-2", _google_clients5),
    ("MyMemory", _mymemory),
    ("Lingva", _lingva),
    ("LibreTranslate", _free_libre),
)


# Имя локального звена в журнале и в окне проверки / the local link's name.
LOCAL_NAME = "DeepL рядом"

# Коды DeepL отличаются от наших: es-MX у DeepL нет, зато есть PT-BR и ZH.
# DeepL codes differ from ours: it has no es-MX but knows PT-BR and ZH.
DLX_CODES: Final[dict[str, str]] = {
    "ru": RU,
    "it": "IT",
    "es": "ES",
    "es-mx": "ES",
    "pt": "PT-PT",
    "pt-br": "PT-BR",
    "zh": "ZH",
    "ja": "JA",
    "de": "DE",
    "fr": "FR",
    "en": "EN-US",
    "tr": "TR",
    "pl": "PL",
    "nl": "NL",
    "ko": "KO",
    "uk": "UK",
    "ar": "AR",
    "cs": "CS",
    "da": "DA",
    "fi": "FI",
    "el": "EL",
    "hu": "HU",
    "id": "ID",
    "nb": "NB",
    "ro": "RO",
    "sk": "SK",
    "sv": "SV",
}


def dlx_code(code: str) -> str:
    """Наш код языка в код DeepL / our language code in DeepL spelling."""
    key = str(code or "").strip().lower()
    if key in ("", "auto"):
        return "auto"
    return DLX_CODES.get(key, key.upper())


def _error_kind(error: Exception) -> str:
    """Return a safe, stable error label without remote text or request data.

    Возвращает безопасную метку ошибки, не сохраняя текст ответа сервера.
    """
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 429:
            return "http 429"
        return f"http {error.code}"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "timeout"
        return "network error"
    if isinstance(error, (ConnectionError, OSError)):
        return "network error"
    return type(error).__name__ or "service error"


def _short(errors: list[str]) -> str:
    """Короткое объяснение для окна: что именно случилось со всеми сервисами.

    A short, human explanation for the window: what went wrong with every service.
    """
    text = " ".join(errors).lower()
    if "429" in text or "too many" in text or "quota" in text:
        return "сервисы заняты, Google ограничил запросы (429)"
    if (
        "timeout" in text
        or "network error" in text
        or "urlopen error" in text
        or "timed out" in text
        or "getaddrinfo" in text
        or "connection" in text
    ):
        return "нет соединения с сервисами перевода"
    return "сервисы не ответили"


def cache_cleanup_due(interval: str, last_cleaned: str | None, now: datetime | None = None) -> bool:
    """Return whether a configured cache-cleanup period has elapsed.

    Timestamps are stored in UTC ISO format. Invalid or missing timestamps are
    treated as due, so enabling the feature cleans a stale cache promptly.
    """
    selected = str(interval or "").lower()
    periods = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
    period = periods.get(selected)
    if selected not in (*periods, "monthly"):
        return False
    try:
        previous = datetime.fromisoformat(str(last_cleaned))
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        else:
            previous = previous.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if selected == "monthly":
        month_index = previous.month  # add exactly one calendar month
        year = previous.year + (month_index // 12)
        month = month_index % 12 + 1
        day = min(previous.day, calendar.monthrange(year, month)[1])
        due_at = previous.replace(year=year, month=month, day=day)
        return current >= due_at
    return current - previous >= period


def cache_cleanup_timestamp(now: datetime | None = None) -> str:
    """Return a stable UTC timestamp for the last cache-cleanup setting."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


class Translator:
    """Перевод в выбранном направлении; результат кладётся в кэш на диске.

    Translation in the chosen direction with an on-disk cache. The cache key
    contains the direction and the language, so switching either of them never
    returns a stale translation.
    """

    def __init__(self, target: str = "it") -> None:
        cache = read_json(CACHE_PATH, {})
        self.cache: dict[str, str] = cache if isinstance(cache, dict) else {}
        self.net_lock = threading.Lock()
        self._cache_lock = threading.RLock()
        self.last = 0.0
        self.out_target = "it"  # выбранный язык перевода / chosen language
        self.direction = "out"  # "out" | "in"
        self.target = "it"
        self.source = "ru"
        self._saved_at = 0.0  # когда кэш писался на диск / last flush
        self._dirty = False  # есть несохранённое / unsaved changes
        # локальный сервис DeepL: подключается, только если модуль включён
        # the local DeepL service: attached only while the module is enabled
        self.local: Any = None
        self.set_target(target)

    # ------------------------------------------------------------------ режим
    @staticmethod
    def is_reverse(direction: str) -> bool:
        """True, если направление — «ваш язык → русский».

        True when the direction is "your language into Russian".
        """
        return str(direction).strip().lower() in IN_ALIASES

    def set_direction(self, direction: str) -> str:
        """Переключить направление: "out" (ru → язык) или "in" (язык → ru).

        Switch the direction: "out" (Russian into the target language) or
        "in" (anything into Russian).
        """
        self.direction = "in" if self.is_reverse(direction) else "out"
        if self.direction == "in":
            self.target, self.source = RU, "auto"
        else:
            self.target = get_lang(code_of(self.out_target))["tr"]
            self.source = "ru"
        log.info("Направление перевода: %s -> %s", self.source, self.target)
        return self.direction

    def set_target(self, target: str) -> str:
        """Сменить язык перевода (код из langs.py). В режиме "in" запоминается.

        Change the target language; in the "in" direction it is only remembered.
        """
        self.out_target = target
        if self.direction != "in":
            code = get_lang(code_of(target))["tr"]
            if code != self.target:
                self.target = code
                log.info("Язык перевода: %s", code)
        else:
            self.set_direction("in")
        return self.target

    # --------------------------------------------------------------- сервисы
    @staticmethod
    def _available(name: str, now: float) -> bool:
        """Не остывает ли сервис прямо сейчас / is the service out of cooldown."""
        with _cool_lock:
            return _cool.get(name, 0) <= now

    @staticmethod
    def _cool_down(name: str, now: float) -> None:
        """Убрать занятый сервис из цепочки на COOL секунд / start a cooldown."""
        with _cool_lock:
            _cool[name] = now + COOL

    # --------------------------------------------------------------- перевод
    def _chain(self) -> list[tuple[str, ServiceFunc]]:
        """Цепочка сервисов на этот запрос / the service chain for this request.

        Если подключён локальный сервис DeepL, он идёт первым: качество выше,
        а при любой его ошибке управление сразу переходит к обычным сервисам.
        A connected local DeepL service goes first: it is better, and on any
        error the regular services take over at once.
        """
        chain = list(SERVICES)
        if self.local is not None:
            chain.insert(0, (LOCAL_NAME, self._via_local))
        return chain

    def _via_local(self, text: str, target: str, source: str = RU) -> str:
        """Перевод через локальный сервис / translation through the local service."""
        return self.local.translate(text, dlx_code(source), dlx_code(target))

    @measure_call("translation")
    def translate(self, text: str) -> str:
        """Перевести текст, идя по цепочке сервисов до первого ответа.

        Translate the text, walking the service chain until one of them answers.
        Raises TranslateError with a human-readable reason when nothing worked.
        """
        key = text.strip()
        if not key:
            return ""
        cache_key = (
            ("in" if self.direction == "in" else "out") + "\x1f" + self.target + "\x1f" + key
        )
        if cache_key in self.cache:
            return self.cache[cache_key]

        errors: list[str] = []
        target, source = self.target, self.source
        started = time.monotonic()
        deadline = started + DEADLINE
        with self.net_lock, _request_deadline_scope(deadline):
            # запросы строго по одному / one at a time
            if cache_key in self.cache:
                return self.cache[cache_key]
            for name, func in self._chain():
                now = time.monotonic()
                if now >= deadline:
                    errors.append("время ожидания истекло")
                    break
                if not self._available(name, now):
                    errors.append(f"{name}: недавно был занят")
                    continue
                wait = MIN_GAP - (now - self.last)
                if wait > 0:
                    time.sleep(min(wait, max(0.0, deadline - time.monotonic())))
                if time.monotonic() >= deadline:
                    errors.append("время ожидания истекло")
                    break
                try:
                    result = (func(key, target, source) or "").strip()
                    self.last = time.monotonic()
                    if result:
                        self._store(cache_key, result)
                        log.info(
                            "Translation succeeded via %s (%s->%s, chars=%d)",
                            name,
                            source,
                            target,
                            len(key),
                        )
                        return result
                    errors.append(f"{name}: пустой ответ")
                except Exception as error:
                    now = time.monotonic()
                    self.last = now
                    errors.append(f"{name}: {_error_kind(error)}")
                    if _is_busy(error):
                        self._cool_down(name, now)
        log.warning("Перевод не удался: %s", "; ".join(errors))
        raise TranslateError(f"{_short(errors)} ({'; '.join(errors)[:160]})")

    def _store(self, key: str, value: str) -> None:
        """Положить перевод в кэш; на диск — не чаще раза в две секунды.

        Cache the translation; the file is written at most every two seconds.

        Зачем не сразу: строка чата переводится по несколько раз за минуту, и
        каждая запись — это перезапись всего файла на две тысячи записей. Раз в
        пару секунд хватает: при выходе кэш дописывается отдельно.
        Why not immediately: a chat line is translated several times a minute and
        every save rewrites the whole file with two thousand entries. Twice a
        second is enough, and the cache is flushed on exit as well.
        """
        with self._cache_lock:
            self.cache[key] = value
            while len(self.cache) > CACHE_MAX:
                self.cache.pop(next(iter(self.cache)))
            self._dirty = True
            should_save = time.monotonic() - self._saved_at >= CACHE_SAVE_EVERY
        if should_save:
            self.flush_cache()

    def clear_cache(self) -> None:
        """Remove all cached translations both from memory and persistent storage."""
        with self._cache_lock:
            # Persist the empty cache before mutating memory: if the disk is
            # read-only, the caller gets an error and the current cache survives.
            write_json(CACHE_PATH, {}, compact=True)
            self.cache.clear()
            self._dirty = False
            self._saved_at = time.monotonic()

    def flush_cache(self) -> None:
        """Дописать кэш на диск, если есть что / persist the cache when needed."""
        # Keep mutation and serialization under one lock: shutdown may flush while
        # the translation worker is inserting a just-completed result.
        with self._cache_lock:
            if not self._dirty:
                return
            try:
                write_json(CACHE_PATH, self.cache, compact=True)
                self._saved_at = time.monotonic()
                self._dirty = False
            except OSError:
                log.exception("Не удалось сохранить кэш")
