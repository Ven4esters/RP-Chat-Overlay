"""Локальный сервис перевода DLX (DeepL) и управление им / the local DLX service.

Зачем это нужно / why it exists
-------------------------------
DLX — отдельная программа (Go, лицензия MIT), которая поднимает на localhost
HTTP-перевод поверх движка DeepL. Мы запускаем её как дочерний процесс, следим
за ним и переводим через неё первой, пока пользователь сам не отключит модуль.
DLX is a separate MIT-licensed Go program that serves DeepL translations over
localhost HTTP. We run it as a child process, supervise it, and use it first
unless the user switches the module off.

Что здесь есть / what lives here
--------------------------------
  * выбор свободного порта и токен доступа, чтобы сервисом не пользовался
    кто попало; a free port plus an access token, so nobody else can use it;
  * запуск, остановка, перезапуск, запрет сирот (Windows job object);
    start, stop, restart and no orphan processes (a Windows job object);
  * health-check коротким запросом и понятный статус для интерфейса;
    a short health-check request and a status the interface can show;
  * наблюдение за процессом: если пользователь или система его убили,
    об этом сообщается, а не молча теряется перевод;
    supervision: if the process is killed, the app says so instead of silently
    losing translation;
  * установка и обновление бинарника с GitHub — только с согласия человека.
    install and update the binary from GitHub, only with the user's consent.

Правила, которых держится модуль / rules this module keeps
---------------------------------------------------------
  * сервис слушает только 127.0.0.1; the service binds to 127.0.0.1 only;
  * при любой поломке перевод падает на обычную цепочку сервисов, а не ломает
    программу; any failure falls back to the regular service chain;
  * выключенный модуль не оставляет висящих процессов; a disabled module leaves
    no processes behind.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from app.config import DATA, log, read_json, write_json

# ---------------------------------------------------------------- постоянные
DLX_DIR = DATA / "dlx"
BINARY_NAME = "dlx.exe" if sys.platform == "win32" else "dlx"
LICENSE_URL = "https://raw.githubusercontent.com/OwO-Network/DLX/main/LICENSE"
RELEASE_API = "https://api.github.com/repos/OwO-Network/DLX/releases/latest"
PORT_RANGE = (1188, 1210)
HEALTH_PHRASE = "ciao come stai"
HEALTH_TIMEOUT = 1.5
TRIAL_TIMEOUT = 5.0             # пробный перевод через прокси / trial via a proxy
START_TIMEOUT = 8.0
RESTART_WINDOW = 600.0          # окно подсчёта падений / crash counting window
RESTART_MAX = 3                 # столько перезапусков за окно / restarts per window

EventFn = Callable[[str, str], None]


class DlxError(Exception):
    """Ошибка сервиса с причиной для человека / a service error with a reason."""


# ------------------------------------------------------------------ утилиты
# Локальные запросы идут мимо любых прокси. Если VPN включил системный прокси
# (а Windows отдаёт его urllib автоматически), обращение к 127.0.0.1 уезжает в
# прокси и возвращается ни с чем — сервис при этом жив и молчит «по вине» сети.
# Local requests bypass every proxy. When a VPN switches the system proxy on
# (Windows hands it to urllib automatically), a call to 127.0.0.1 travels to the
# proxy and comes back empty, while the service is alive and looks dead.
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_post_json(url: str, payload: dict, headers: dict | None,
                    timeout: float, local: bool = True) -> Any:
    """POST с JSON-телом и разбором ответа / POST a JSON body and parse the reply.

    `local=True` — запрос к самому сервису на 127.0.0.1: без прокси.
    `local=True` means a call to the service on 127.0.0.1, so no proxy.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    opener = _LOCAL_OPENER if local else urllib.request.urlopen
    with opener.open(request, timeout=timeout) as answer:
        return json.loads(answer.read().decode("utf-8", "replace"))


def _http_get_json(url: str, timeout: float = 6.0) -> Any:
    """GET с JSON-ответом (для проверки обновлений) / GET returning JSON."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "RP-Chat-Overlay")
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.loads(answer.read().decode("utf-8", "replace"))


def free_port(low: int = PORT_RANGE[0], high: int = PORT_RANGE[1]) -> int:
    """Свободный порт на localhost / a free localhost port.

    Сначала пробуем привычный 1188, затем соседние: занятый порт — частая
    причина «сервис не запустился». The usual 1188 comes first, then its
    neighbours, because a busy port is a common reason for a dead service.
    """
    for port in range(low, high + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise DlxError("нет свободного порта для локального сервиса")


def _mask_url(url: str) -> str:
    """Адрес без логина и пароля — для журнала и интерфейса.

    The address without its user and password, for the log and the interface.

    Зачем: у прокси с авторизацией адрес выглядит как
    `http://user:pass@host:port`, и он попадает в `app.log`, в `errors.log` и
    в подпись состояния. Пароль от чужого прокси в журнале — это утечка.
    Why: a proxy with authorisation looks like `http://user:pass@host:port`, and
    that string reaches `app.log`, `errors.log` and the state line. Somebody
    else's proxy password in a log is a leak.
    """
    text = (url or "").strip()
    if not text:
        return ""
    try:
        parts = urllib.parse.urlsplit(text if "://" in text else "http://" + text)
    except ValueError:
        return "***"
    if not (parts.username or parts.password):
        return text
    host = parts.hostname or "?"
    netloc = f"***:***@{host}" + (f":{parts.port}" if parts.port else "")
    return urllib.parse.urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def normalize_proxy(value: str) -> str:
    """Приводит адрес прокси к виду, который понимает DLX; пустая строка — «нет».

    Turns a proxy address into the form DLX understands; an empty result means
    "no proxy". Why this exists: DLX parses `-proxy` with url.Parse and calls
    log.Fatalf on a malformed value, so a typo would kill the service at launch
    with a bare exit code. Better to drop a bad value here and say so in the log.
    """
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text            # «127.0.0.1:8080» тоже годится
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in ("http", "https", "socks5", "socks5h"):
        log.warning("DLX: прокси %s не поддержан (нужен http, https или socks5)",
                    _mask_url(text))
        return ""
    if not parsed.hostname or not parsed.port:
        log.warning("DLX: в адресе прокси %s нет хоста или порта — игнорирую",
                    _mask_url(text))
        return ""
    return text


def check_proxy(value: str, timeout: float = 4.0) -> tuple[bool, str]:
    """Проверяет прокси до запуска сервиса / checks the proxy before launch.

    Возвращает (годен, пояснение для человека). Протокол определяется по ответу:
    HTTP-прокси отвечает на CONNECT строкой «HTTP/1.1 200», SOCKS5 — байтами
    0x05 0x00. Это важно: на адрес SOCKS5, переданный как http://, DLX вешается
    в ожидании и не отвечает вовсе, и понять причину по журналу нельзя.
    Returns (usable, a human explanation). The protocol is recognised by the reply:
    an HTTP proxy answers CONNECT with "HTTP/1.1 200", SOCKS5 answers 0x05 0x00.
    This matters: DLX given a SOCKS5 address as http:// just hangs, and the log
    says nothing useful.
    """
    url = normalize_proxy(value)
    if not url:
        return True, ""
    parsed = urllib.parse.urlparse(url)
    host, port = parsed.hostname, parsed.port
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            if parsed.scheme.startswith("socks"):
                sock.sendall(b"\x05\x01\x00")           # приветствие SOCKS5
                reply = sock.recv(2)
                if reply[:1] == b"\x05" and reply[1:2] != b"\xff":
                    return True, ""
                return False, (f"{host}:{port} не отвечает как socks5 — "
                               f"возможно, это HTTP-прокси: http://{host}:{port}")
            target = "oneshot-free.www.deepl.com:443"
            sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n"
                         .encode("ascii", "replace"))
            head = sock.recv(64)
            if head.startswith(b"HTTP/") and b" 200" in head[:24]:
                return True, ""
            if head[:1] == b"\x05":
                return False, (f"{host}:{port} отвечает как socks5, а не как "
                               f"HTTP-прокси — нужно socks5://{host}:{port}")
            return False, (f"{host}:{port} не принял CONNECT — похоже, это не "
                           f"прокси, а обычный сервер")
    except socket.timeout:
        return False, f"прокси {host}:{port} не ответил за {timeout:.0f} с"
    except OSError as error:
        return False, (f"прокси {host}:{port} недоступен: "
                       f"{error.strerror or error}")


GEO_URL = "https://ipinfo.io/json"     # откуда узнаём страну выхода / exit lookup


def system_proxy() -> str:
    """Прокси, который включил VPN в настройках Windows (если включил).

    The proxy a VPN switched on in the Windows settings, when it did.
    Зачем: VPN в режиме «системный прокси» ставит адрес в реестр, и Windows
    отдаёт его программам. DLX — программа на Go, реестр она не смотрит, поэтому
    без этого шага DeepL видел бы российский адрес, хотя VPN включён.
    Why: a VPN in system-proxy mode writes its address to the registry and Windows
    hands it to applications. DLX is a Go program and does not read the registry,
    so without this step DeepL would see a Russian address while the VPN is on.
    """
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion"
                             r"\Internet Settings")
        with key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except (OSError, ImportError, FileNotFoundError):
        return ""
    if not enabled or not server:
        return ""
    text = str(server).split(";")[0].strip()        # «http=host:port;https=…»
    if "=" in text:
        text = text.split("=", 1)[1]
    return normalize_proxy(text)     # откуда узнаём страну выхода / exit lookup


def _proxy_socket(proxy: str, host: str, port: int, timeout: float) -> socket.socket:
    """Открывает туннель до host:port через прокси (http CONNECT или socks5).

    Opens a tunnel to host:port through the proxy (http CONNECT or socks5).
    Отдельная функция, потому что стандартный urllib SOCKS5 не умеет вовсе.
    A separate helper, because plain urllib cannot do SOCKS5 at all.
    """
    parsed = urllib.parse.urlparse(proxy)
    sock = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        if parsed.scheme.startswith("socks"):
            user = urllib.parse.unquote(parsed.username or "")
            password = urllib.parse.unquote(parsed.password or "")
            methods = b"\x00\x02" if user else b"\x00"
            sock.sendall(b"\x05" + bytes([len(methods)]) + methods)
            answer = sock.recv(2)
            if answer[:1] != b"\x05":
                raise OSError("прокси не ответил на приветствие SOCKS5")
            if answer[1:2] == b"\x02":
                if not user:
                    raise OSError("прокси требует логин и пароль")
                sock.sendall(b"\x01" + bytes([len(user)]) + user.encode("utf-8")
                             + bytes([len(password)]) + password.encode("utf-8"))
                if sock.recv(2)[1:2] != b"\x00":
                    raise OSError("прокси не принял логин и пароль")
            elif answer[1:2] != b"\x00":
                raise OSError("прокси не принял способ подключения")
            raw_host = host.encode("idna") if not host.replace(".", "").isdigit() else None
            if raw_host:
                request = (b"\x05\x01\x00\x03" + bytes([len(raw_host)]) + raw_host)
            else:
                request = b"\x05\x01\x00\x01" + socket.inet_aton(host)
            sock.sendall(request + port.to_bytes(2, "big"))
            head = sock.recv(4)
            if head[1:2] != b"\x00":
                raise OSError(f"прокси отказал в соединении (код {head[1:2].hex()})")
            extra = {1: 4, 4: 16}.get(head[3], 0)
            if head[3] == 3:
                extra = sock.recv(1)[0]
            remaining = extra + 2
            while remaining > 0:
                chunk = sock.recv(remaining)
                if not chunk:
                    break
                remaining -= len(chunk)
            return sock
        # HTTP-прокси: CONNECT и проверка ответа
        # an HTTP proxy: CONNECT and a reply check
        target = f"{host}:{port}"
        sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n"
                     .encode("ascii"))
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 2048:
            chunk = sock.recv(256)
            if not chunk:
                break
            head += chunk
        if b" 200" not in head[:32]:
            raise OSError(f"прокси не открыл туннель: {head.splitlines()[:1]}")
        return sock
    except Exception:
        sock.close()
        raise


def proxy_exit(proxy: str, timeout: float = 10.0) -> tuple[bool, str]:
    """Узнаёт, из какой страны выходит прокси / finds the proxy's exit country.

    Возвращает (получилось, текст для человека). Запрос идёт на ipinfo.io через
    сам прокси — иначе мы увидели бы свой адрес, а не его.
    Returns (ok, a human readable line). The lookup goes to ipinfo.io through the
    proxy itself, otherwise we would see our own address instead of its.
    """
    url = normalize_proxy(proxy)
    if not url:
        return False, "прокси не задан"
    lookup = urllib.parse.urlsplit(GEO_URL)
    host, path = lookup.hostname or "ipinfo.io", lookup.path or "/json"
    try:
        sock = _proxy_socket(url, host, 443, timeout)
    except socket.timeout:
        return False, "прокси не ответил при подключении"
    except OSError as error:
        return False, f"прокси не открыл туннель: {error}"
    try:
        context = ssl.create_default_context()
        with context.wrap_socket(sock, server_hostname=host) as tls:
            tls.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                         "User-Agent: RP-Chat-Overlay\r\nConnection: close\r\n\r\n")
                        .encode("ascii"))
            raw = b""
            while True:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                raw += chunk
    except (OSError, ssl.SSLError) as error:
        return False, f"через прокси не открылся https: {error}"
    finally:
        try:
            sock.close()
        except OSError:
            pass
    body = raw.split(b"\r\n\r\n", 1)[-1]
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return False, "ответ сервиса проверки не разобрать"
    ip = str(data.get("ip") or "")
    country = str(data.get("country") or "?")
    org = str(data.get("org") or "")
    city = str(data.get("city") or "")
    where = ", ".join(part for part in (city, org) if part)
    if not ip:
        return False, "сервис проверки не назвал адрес"
    line = f"{ip} ({country}{' · ' + where if where else ''})"
    if country.upper() == "RU":
        return False, line + " — выход из России, DeepL такой адрес не примет"
    return True, line


def loopback_ok() -> tuple[bool, str]:
    """Работают ли соединения внутри машины / do local connections work at all.

    Иногда VPN или файрвол перехватывает даже 127.0.0.1: тогда любой локальный
    сервис выглядит мёртвым, и виноват не он. Проверяем на своём сокете.
    A VPN or a firewall sometimes intercepts even 127.0.0.1, and then any local
    service looks dead while it is not. We check with a socket of our own.
    """
    try:
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            client.sendall(b"ping")
            conn, _ = server.accept()
            with conn:
                if conn.recv(4) != b"ping":
                    return False, "локальное соединение вернулось без ответа"
        return True, ""
    except OSError as error:
        return False, f"локальные соединения не работают: {error}"
    finally:
        try:
            server.close()
        except (OSError, UnboundLocalError):
            pass


def _port_owner(port: int) -> str:
    """Кто слушает порт: «dlx.exe (pid 1234)» или пустая строка.

    Who listens on the port: "dlx.exe (pid 1234)" or an empty string.
    Нужно, чтобы отличить «порт занят нашим же зависшим процессом» от «порт
    занят чужой программой» — лечится это по-разному.
    It separates "our own stuck process holds the port" from "another program
    does", because the cure is different.
    """
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True,
                             timeout=6, creationflags=0x08000000)
        for line in out.stdout.decode("cp866", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") \
                    and parts[3].upper() == "LISTENING":
                pid = parts[4]
                names = subprocess.run(["tasklist", "/FI", f"PID eq {pid}",
                                        "/FO", "CSV", "/NH"], capture_output=True,
                                       timeout=6, creationflags=0x08000000)
                text = names.stdout.decode("cp866", "replace").strip().strip('"')
                owner = text.split('","')[0]
                return f"{owner} (pid {pid})"
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""
    return ""


def _kill_port_owner(port: int) -> None:
    """Закрывает наш зависший dlx.exe, занявший порт / kills our stuck dlx.exe."""
    if sys.platform != "win32":
        return
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True,
                             timeout=6, creationflags=0x08000000)
        for line in out.stdout.decode("cp866", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") \
                    and parts[3].upper() == "LISTENING":
                subprocess.run(["taskkill", "/F", "/PID", parts[4]],
                               capture_output=True, timeout=6,
                               creationflags=0x08000000)
                log.info("DLX: закрыл зависший процесс на порту %s (pid %s)",
                         port, parts[4])
                return
    except (OSError, subprocess.SubprocessError):
        log.exception("DLX: не удалось освободить порт %s", port)


def _is_pe_file(path: Path) -> bool:
    """Похоже ли скачанное на целую Windows-программу.

    Does the download look like a complete Windows program: an MZ header, a PE
    signature where the header says it is, and a plausible size. A truncated or
    interleaved file passes a bare "MZ" check and then fails at launch with
    WinError 193, which is exactly what happened once.
    """
    try:
        size = path.stat().st_size
        if size <= 512 * 1024:
            return False
        with path.open("rb") as handle:
            head = handle.read(0x40)
            if head[:2] != b"MZ":
                return False
            offset = int.from_bytes(head[0x3C:0x40], "little")
            if offset <= 0 or offset + 4 > size:
                return False
            handle.seek(offset)
            return handle.read(4) == b"PE\x00\x00"
    except OSError:
        return False


def _kill_orphans_with_job(handle: int) -> int | None:
    """Windows: job object, который гасит дочерний процесс вместе с нашим.

    On Windows a job object with KILL_ON_JOB_CLOSE terminates the child when the
    parent dies, even if the parent crashed. Returns the job handle or None.
    """
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", ctypes.c_uint32),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", ctypes.c_uint32),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", ctypes.c_uint32),
                        ("SchedulingClass", ctypes.c_uint32)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("ReadOperationCount", "WriteOperationCount",
                         "OtherOperationCount", "ReadTransferCount",
                         "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits),
                        ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000   # KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(job, 9, ctypes.byref(info),
                                         ctypes.sizeof(info))
        kernel32.AssignProcessToJobObject(job, handle)
        return job
    except Exception:                                    # job object — необязательный бонус
        log.exception("Не удалось создать job object для DLX")
        return None


# ------------------------------------------------------------------- сервис
class DlxService:
    """Управление локальным сервисом DLX / supervision of the local DLX service.

    cfg       настройки программы / the program settings
    command   своя команда запуска (нужна тестам и нестандартным сборкам);
              a custom command line, used by tests and unusual builds
    on_event  callback(kind, text) для сообщений игроку; callback for messages
    """

    def __init__(self, cfg: Mapping[str, Any] | None = None,
                 command: list[str] | None = None,
                 on_event: EventFn | None = None,
                 directory: Path | None = None) -> None:
        self.cfg: Mapping[str, Any] = cfg or {}
        self.dir = Path(directory or DLX_DIR)
        self.binary = self.dir / BINARY_NAME
        self.command = command
        self.on_event = on_event
        self._process: subprocess.Popen | None = None
        self._job: int | None = None
        self._port: int = 0
        self._token: str = ""
        # off | missing | starting | ready | upstream | error
        self._state: str = "off"          # upstream = жив, но DeepL отказал
        self._spawn: dict[str, str] = {}  # с какими параметрами запущен / launch args
        self._proxy_error = ""            # почему прокси не годится / proxy verdict
        self._note = ""                   # оговорка к состоянию / a state remark
        self._probe_logged = False        # жалоба на молчание — один раз / log once
        self._probe_error = ""            # чем именно ответил сервис / what it said
        self._install_lock = threading.Lock()   # одна установка за раз / one at a time
        self._reason: str = ""
        self._lock = threading.RLock()
        self._stop_watch = threading.Event()
        self._watch_thread: threading.Thread | None = None
        self._crashes: list[float] = []
        self._last_attempt = 0.0
        atexit.register(self.shutdown)

    # ---------------------------------------------------------------- свойства
    def enabled(self) -> bool:
        """Включён ли модуль в настройках / is the module switched on."""
        return bool(self.cfg.get("dlx_enabled"))

    def external_url(self) -> str:
        """Адрес своего сервиса вместо dlx.exe / a service of your own.

        Пусто — работаем со своим dlx.exe. Если задан (локальный сервер на
        Node.js, развёрнутый DeepLX, свой хост) — бинарник не нужен вовсе.
        Empty means the bundled dlx.exe. When set (a local Node.js server, a
        deployed DeepLX, your own host) no binary is needed at all.
        """
        return str(self.cfg.get("dlx_url") or "").strip().rstrip("/")

    def _external_base(self) -> str:
        """Адрес без хвоста /translate / the address without the route tail.

        Люди копируют адрес целиком — вместе с `/api/translate` (так его пишут
        в чужих инструкциях). Хвост отрезаем, маршрут добавляем сами.
        People paste the address whole, `/api/translate` included, as other
        instructions show it. The tail is dropped, the route is added by us.
        """
        url = self.external_url()
        for tail in ("/api/translate", "/v1/translate", "/v2/translate",
                     "/translate"):
            if url.endswith(tail):
                url = url[: -len(tail)]
                break
        return url

    def installed(self) -> bool:
        """Есть ли бинарник на диске / is the binary present."""
        if self.command or self.external_url():
            return True
        return self.binary.is_file()

    @property
    def port(self) -> int:
        """Порт, на котором работает сервис / the port the service listens on."""
        return self._port

    @property
    def token(self) -> str:
        """Токен доступа к локальному сервису / the local access token."""
        return self._token

    def version(self) -> str:
        """Версия установленного сервиса / the installed service version."""
        meta = read_json(self.dir / "version.json", {}) or {}
        return str(meta.get("version") or "") if isinstance(meta, dict) else ""

    def status(self) -> dict[str, Any]:
        """Состояние для интерфейса / the state for the interface."""
        with self._lock:
            return {"state": self._state, "port": self._port,
                    "version": self.version(), "reason": self._reason,
                    "note": self._note,
                    "installed": self.installed(), "running": self._alive()}

    # ------------------------------------------------------------------ токен
    def _load_token(self) -> str:
        """Токен из файла или новый / the stored token or a fresh one."""
        path = self.dir / "token.txt"
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if not token:
            token = secrets.token_hex(16)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(token, encoding="utf-8")
            except OSError:
                log.exception("Не удалось сохранить токен DLX")
        return token

    def rotate_token(self) -> str:
        """Выпустить новый токен (сервис перезапускается).

        Issue a new token; the running service is restarted.
        """
        path = self.dir / "token.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_hex(16), encoding="utf-8")
        except OSError as error:
            raise DlxError(f"не удалось записать токен: {error}") from error
        self._token = ""
        if self._alive():
            self.restart()
        return self._ensure_token()

    def _ensure_token(self) -> str:
        if not self._token:
            self._token = self._load_token()
        return self._token

    # ------------------------------------------------------------- управление
    def _alive(self) -> bool:
        """Процесс запущен и не завершился / the child process is running.

        Свой сервис по адресу живёт отдельно от программы — за ним не следим,
        его состояние видно только по ответу на запрос.
        A service of your own lives outside the program, so there is nothing to
        supervise: its state shows up in the answers alone.
        """
        if self.external_url():
            return True
        proc = self._process
        return proc is not None and proc.poll() is None

    def _auth(self) -> dict[str, str]:
        """Заголовок авторизации / the authorization header.

        Токен приводится к ASCII: заголовок HTTP не умеет кириллицу, и вставленный
        из буфера токен иначе валил бы запрос ещё до отправки.
        The token is reduced to ASCII: an HTTP header cannot carry non-Latin
        characters, and a pasted token would otherwise break before sending.
        """
        if self.external_url():
            token = str(self.cfg.get("dlx_url_token") or "").strip()
            clean = "".join(ch for ch in token if " " <= ch <= "~")
            if clean != token:
                log.warning("DLX: в токене своего сервиса недопустимые символы — "
                            "они отброшены")
            return {"Authorization": f"Bearer {clean}"} if clean else {}
        return {"Authorization": f"Bearer {self._token}"}

    def resolve_proxy(self) -> str:
        """Адрес прокси, который пойдёт в DLX; пустая строка — без прокси.

        The proxy address that will be passed to DLX; an empty string means none.
        Если http-адрес на самом деле SOCKS5, схема подменяется: иначе сервис
        повиснет на первом же переводе. Если прокси указан, но недоступен —
        причина остаётся в `self._proxy_error`, и запуск не делается.
        When an http address is really SOCKS5 the scheme is swapped, otherwise the
        service hangs on the first translation. When a proxy is configured but
        unreachable, the reason stays in `self._proxy_error` and we do not start.
        """
        self._proxy_error = ""
        url = normalize_proxy(str(self.cfg.get("dlx_proxy") or ""))
        if not url and self.cfg.get("dlx_use_system_proxy", True):
            # своего прокси нет — берём тот, что включил VPN в Windows
            # no proxy of our own, so take the one the VPN switched on
            url = system_proxy()
            if url:
                ok, why = check_proxy(url)
                if ok:
                    log.info("DLX: использую системный прокси Windows %s",
                             _mask_url(url))
                    return url
                log.warning("DLX: системный прокси %s не отвечает (%s) — иду "
                            "напрямую", _mask_url(url), why)
                return ""
        if not url:
            return ""
        ok, why = check_proxy(url)
        if ok:
            return url
        parsed = urllib.parse.urlparse(url)
        alt_scheme = "http" if parsed.scheme.startswith("socks") else "socks5"
        alt = f"{alt_scheme}://{parsed.hostname}:{parsed.port}"
        ok_alt, why_alt = check_proxy(alt)
        if ok_alt:
            log.info("DLX: прокси %s распознан как %s", _mask_url(url),
                     _mask_url(alt))
            return alt
        self._proxy_error = why or why_alt
        log.warning("DLX: прокси не годится — %s", self._proxy_error)
        return ""

    def _command_line(self, port: int, token: str, proxy: str = "") -> list[str]:
        """Команда запуска / the command line to start.

        Флаги взяты из документации DLX (`-ip`, `-port`, `-token`, `-s`, `-proxy`).
        `-ip 127.0.0.1` обязателен: по умолчанию сервис слушает 0.0.0.0, то есть
        был бы виден всей локальной сети.
        The flags come from the DLX documentation (`-ip`, `-port`, `-token`, `-s`,
        `-proxy`). `-ip 127.0.0.1` is mandatory: by default the service binds
        0.0.0.0, which would expose it to the whole local network.
        """
        if self.command:
            cmd = [str(part).format(port=port, token=token) for part in self.command]
        else:
            cmd = [str(self.binary), "-ip", "127.0.0.1", "-port", str(port),
                   "-token", token]
        # необязательные параметры: прокси и токен DeepL Pro
        # optional parameters: an HTTP proxy and a DeepL Pro token
        pro = str(self.cfg.get("dlx_pro_token") or "").strip()
        if proxy:
            cmd += ["-proxy", proxy]
        if pro:
            cmd += ["-s", pro]
        # в снимок идёт значение из настроек, а не подменённое: иначе автоподмена
        # схемы заставляла бы перезапускать сервис при каждом сохранении
        # the snapshot keeps the configured value, not the swapped one: otherwise
        # the scheme fallback would restart the service on every save
        self._spawn = {"proxy": normalize_proxy(str(self.cfg.get("dlx_proxy") or "")),
                       "pro": pro, "used": proxy}
        return cmd

    def needs_restart(self) -> bool:
        """Изменились ли параметры запуска / did the launch parameters change."""
        used = self._spawn or {}
        if self.external_url() or used.get("url"):
            # адрес поменяли — старый сервис больше не наш
            # the address changed, so the old service is not ours any more
            return bool(used) and used.get("url") != self.external_url()
        now = {"proxy": normalize_proxy(str(self.cfg.get("dlx_proxy") or "")),
               "pro": str(self.cfg.get("dlx_pro_token") or "").strip()}
        return bool(used) and (used.get("proxy"), used.get("pro")) != (now["proxy"], now["pro"])

    def start(self) -> bool:
        """Запустить сервис и дождаться ответа.

        Start the service and wait until it answers.

        Порты перебираются: если настроенный молчит или занят чужой программой,
        пробуем соседние свободные — иначе один занятый порт навсегда выключал
        DeepL. Зависший dlx.exe с того же порта закрываем: «сирот» быть не должно.
        Ports are tried in turn: when the configured one is silent or taken by
        another program, free neighbours are used, otherwise one busy port would
        disable DeepL forever. A stuck dlx.exe on that port is killed, because no
        orphans should survive.
        """
        with self._lock:
            if self.external_url():
                return self._start_external()
            if self._alive():
                return True
            # защита от повторов: два обработчика сразу после неудачи не должны
            # поднимать сервис по кругу / a repeat guard: two callbacks after a
            # failure must not start the service in a loop
            now = time.time()
            if self._state in ("error", "off") and now - self._last_attempt < 4.0:
                log.info("DLX: повторный запуск отложен (%.1f с назад была попытка)",
                         now - self._last_attempt)
                return False
            self._last_attempt = now
            if not self.installed():
                self._set_state("missing", "сервис не установлен")
                return False
            token = self._ensure_token()
            proxy = self.resolve_proxy()
            if self._proxy_error:
                # прокси указан, но не работает: запускать бессмысленно
                # a proxy is configured but dead, so starting makes no sense
                self._set_state("error", self._proxy_error)
                return False
            self._note = self._note_text(proxy)
            ok, why = loopback_ok()
            if not ok:
                # ни один порт не поможет: сломаны сами локальные соединения
                # no port will help: local connections themselves are broken
                self._set_state("error", f"{why} — проверьте VPN и файрвол")
                log.warning("DLX: %s", why)
                return False
            wanted = int(self.cfg.get("dlx_port") or 0)
            candidates: list[int] = [wanted] if wanted else []
            for _ in range(3):
                free = free_port()
                if free not in candidates:
                    candidates.append(free)
            reason = ""
            for index, port in enumerate(candidates):
                owner = _port_owner(port)
                if owner and "dlx" in owner.lower():
                    log.info("DLX: порт %s держит старый процесс %s", port, owner)
                    _kill_port_owner(port)
                    time.sleep(0.4)
                elif owner:
                    log.info("DLX: порт %s занят программой %s — беру другой", port, owner)
                    continue
                ok, reason = self._try_start(port, token, proxy)
                if ok:
                    if index or port != (wanted or port):
                        self._note = " · ".join(part for part in (
                            self._note, f"порт {port}") if part)
                        log.info("DLX: работаю на запасном порту %s", port)
                    return True
                if self._state == "upstream":
                    return False          # порт тут не при чём / the port is fine
                self.stop()
            self._set_state("error", reason or "сервис не ответил")
            return False

    def _note_text(self, proxy: str) -> str:
        """Пояснение к состоянию: откуда взялся прокси / where the proxy came from."""
        configured = normalize_proxy(str(self.cfg.get("dlx_proxy") or ""))
        if proxy and not configured:
            host = urllib.parse.urlparse(proxy).hostname or ""
            port = urllib.parse.urlparse(proxy).port
            return f"через системный прокси {host}" + (f":{port}" if port else "")
        if proxy and proxy != configured:
            return f"прокси распознан как {proxy.split('://')[0]}"
        return ""

    def _start_external(self) -> bool:
        """Подключиться к своему сервису вместо запуска бинарника.

        Connect to a service of your own instead of starting the binary.

        Здесь нечего запускать: ни файла, ни порта, ни прокси — сервис уже
        работает, надо только убедиться, что он отвечает и переводит.
        Nothing to start here: no file, no port, no proxy. The service runs
        already; all we do is check that it answers and translates.
        """
        url = self.external_url()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            # иначе в поле мог бы попасть file:// или ftp:// — и программа
            # читала бы локальные файлы вместо перевода
            # otherwise file:// or ftp:// could land in the field and the
            # program would read local files instead of translating
            self._set_state("error", "адрес своего сервиса должен начинаться с "
                                     "http:// или https://")
            log.warning("DLX: отклонён адрес своего сервиса %s", _mask_url(url))
            return False
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._spawn = {"url": url}
        state = self.probe()
        if state == "ready":
            self._note = f"свой сервис {parsed.netloc or url}"
            self._set_state("ready", "")
            log.info("DLX: свой сервис %s отвечает", _mask_url(url))
            return True
        if state == "upstream":
            self._note = f"свой сервис {parsed.netloc or url}"
            self._set_state("upstream",
                            "свой сервис работает, но DeepL отказал")
            return False
        self._set_state(
            "error", self._probe_error or
            f"свой сервис {url} не отвечает — проверьте адрес и что он запущен")
        log.warning("DLX: свой сервис %s не отвечает", _mask_url(url))
        return False

    def _try_start(self, port: int, token: str, proxy: str) -> tuple[bool, str]:
        """Одна попытка на конкретном порту / a single attempt on one port."""
        cmd = self._command_line(port, token, proxy)
        env = dict(os.environ, TOKEN=token)
        creation = 0
        startup = None
        if sys.platform == "win32":
            creation = 0x08000000 | 0x00000200      # NO_WINDOW | NEW_PROCESS_GROUP
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            self._process = subprocess.Popen(
                cmd, cwd=str(self.dir), env=env, creationflags=creation,
                startupinfo=startup, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except OSError as error:
            winerror = getattr(error, "winerror", None)
            log.exception("DLX: не удалось запустить %s", cmd)
            if winerror == 193:
                # файл скачался битым — выбрасываем, следующий запуск скачает заново
                # the file came out broken, so drop it and download again next time
                self._drop_binary("файл сервиса повреждён — скачаю заново")
                return False, "файл сервиса повреждён"
            return False, f"не удалось запустить: {error}"
        self._job = _kill_orphans_with_job(int(getattr(self._process, "_handle", 0) or 0))
        self._port = port
        self._token = token
        self._probe_logged = False
        self._set_state("starting", "")
        started = time.time()
        while time.time() - started < START_TIMEOUT:
            if self._process is not None and self._process.poll() is not None:
                code = self._process.returncode
                log.warning("DLX завершился сразу после запуска, код %s", code)
                return False, f"сервис завершился (код {code})"
            verdict = self.probe()
            if verdict == "ready":
                self._set_state("ready", "")
                log.info("DLX запущен: порт %s, версия %s", port, self.version() or "?")
                self._start_watch()
                return True, ""
            if verdict == "upstream":
                # процесс живёт, но DeepL отказал: перезапускать бессмысленно,
                # а игроку нужно знать, что делать / the process is alive but DeepL
                # refused, so a restart is pointless and the player needs the cure
                self._set_state("upstream", "DeepL не отвечает (503) — "
                                            "помогает прокси или токен DeepL Pro")
                log.warning("DLX: сервис запущен, но DeepL отвечает 503 — "
                            "проверьте прокси или токен DeepL Pro")
                self._start_watch()
                return False, "DeepL не отвечает (503)"
            time.sleep(0.5)
        return False, self._why_silent(port)

    def _drop_binary(self, reason: str) -> None:
        """Убрать испорченный файл, чтобы его скачали заново / drop a broken file."""
        try:
            self.binary.unlink(missing_ok=True)
        except OSError:
            log.exception("DLX: не удалось удалить испорченный файл")
        read_json(self.dir / "version.json", {})
        try:
            (self.dir / "version.json").unlink(missing_ok=True)
        except OSError:
            pass
        self._set_state("missing", reason)

    def _why_silent(self, port: int) -> str:
        """Объясняет, почему сервис молчит: порт закрыт или запросы уходят мимо.

        Explains why the service stays silent: a closed port, or requests leaving
        the machine instead of reaching the loopback.
        """
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                busy = True
        except OSError:
            busy = False
        if busy:
            owner = _port_owner(port)
            who = f" ({owner})" if owner else ""
            return (f"порт {port} открыт{who}, но сервис не отвечает — похоже, "
                    f"локальные запросы перехватывает системный прокси, VPN или "
                    f"другая программа")
        owner = _port_owner(port)
        if owner:
            return f"порт {port} занят программой {owner} — беру другой"
        return (f"сервис не занял порт {port} — возможно, порт закрыт правилами "
                f"или не подходит")

    def stop(self) -> None:
        """Остановить сервис / stop the service."""
        with self._lock:
            proc = self._process
            self._process = None
            self._stop_watch.set()
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        log.exception("DLX: не удалось погасить процесс")
            self._job = None
            self._set_state("off", "")

    def restart(self) -> bool:
        """Перезапустить сервис / restart the service."""
        self.stop()
        self._stop_watch = threading.Event()
        return self.start()

    def shutdown(self) -> None:
        """Гашение при выходе программы / the final shutdown hook."""
        try:
            self.stop()
        except Exception:
            pass

    def ensure(self) -> bool:
        """Запустить, если нужно, и вернуть готовность / start if needed.

        Если сервис уже работает, но DeepL отказывал, сначала перепроверяем:
        связь могла восстановиться сама / when the service runs but DeepL was
        refusing, probe again first: the connection may have recovered.
        """
        if not self.enabled():
            return False
        if self._alive() and self._state in ("ready", "upstream"):
            if self.probe() == "ready":
                self._set_state("ready", "")
                return True
            return False
        return self.start()

    # ------------------------------------------------------------- наблюдение
    def _set_state(self, state: str, reason: str) -> None:
        """Запомнить состояние; в журнал — только при смене состояния.

        Remembers the state and logs only transitions, so a repeated failure does
        not fill the log with identical lines.
        """
        if state != self._state:
            log.info("DLX: состояние %s (порт %s)%s", state, self._port or 0,
                     f" — {reason}" if reason else "")
        self._state = state
        self._reason = reason

    def _start_watch(self) -> None:
        """Поток наблюдения за процессом / the supervision thread."""
        if self._watch_thread is not None and self._watch_thread.is_alive():
            return
        self._stop_watch.clear()

        def watch() -> None:
            while not self._stop_watch.wait(3.0):
                proc = self._process
                if proc is None:
                    return
                if proc.poll() is None:
                    continue
                code = proc.returncode
                log.warning("DLX завершился неожиданно, код %s", code)
                self._process = None
                self._set_state("error", "сервис остановлен")
                if self.on_event is not None:
                    self.on_event("stopped",
                                  "Локальный сервис DeepL остановлен — перевожу "
                                  "через стандартные сервисы. Вернуть: "
                                  "Настройки → DeepL → Запустить.")
                now = time.time()
                self._crashes = [t for t in self._crashes if now - t < RESTART_WINDOW]
                if len(self._crashes) >= RESTART_MAX or not self.enabled():
                    return
                self._crashes.append(now)
                if self.start() and self.on_event is not None:
                    self.on_event("restarted", "Локальный сервис DeepL снова работает.")
                if self._process is None:
                    return

        self._watch_thread = threading.Thread(target=watch, name="dlx-watch",
                                              daemon=True)
        self._watch_thread.start()

    # ----------------------------------------------------------- проверка/перевод
    def _url(self, path: str = "/translate") -> str:
        """Куда слать запрос / where to send a request."""
        if self.external_url():
            return f"{self._external_base()}{path}"
        return f"http://127.0.0.1:{self._port or PORT_RANGE[0]}{path}"

    def probe(self, timeout: float = HEALTH_TIMEOUT,
              trial_timeout: float = TRIAL_TIMEOUT) -> str:
        """Что именно с сервисом: готов, жив без DeepL или молчит.

        What exactly is wrong: ready, alive without DeepL, or silent.

        Три разных ответа важны, потому что лечатся они по-разному:
          * `down` — процесс не отвечает вовсе (порт занят, сервис не поднялся);
          * `upstream` — сервис жив, но DeepL вернул 503/429: сеть, лимиты или
            блокировка; помогает прокси или токен DeepL Pro;
          * `ready` — можно переводить.
        The three answers matter because each has its own cure: `down` means the
        process is silent, `upstream` means DeepL itself refused, `ready` means go.
        """
        self._probe_error = ""
        if not self.external_url() and not (self._port and self._alive()):
            return "down"
        # 1. дешёвая проверка живости: GET / не тратит запрос к DeepL
        #    a cheap liveness check: GET / does not spend a DeepL request
        try:
            with _LOCAL_OPENER.open(self._url("/"), timeout=timeout) as answer:
                if answer.status != 200:
                    return "down"
        except (urllib.error.URLError, OSError, ValueError) as error:
            if not self._probe_logged:
                self._probe_logged = True
                log.info("DLX: %s не отвечает: %s", _mask_url(self._url("/")),
                         str(error)[:90])
            return "down"
        # 2. один пробный перевод: работает ли связка с DeepL
        #    one trial translation: does the DeepL link work
        try:
            answer = _http_post_json(
                self._url(), {"text": HEALTH_PHRASE, "source_lang": "IT",
                              "target_lang": "RU"},
                self._auth(), trial_timeout)
        except urllib.error.HTTPError as error:
            if error.code in (429, 503):
                return "upstream"
            if error.code in (401, 403):
                # токен не подошёл — это не «молчит», и лечится иначе
                # a wrong token is not "silent", and it has its own cure
                self._probe_error = "сервис отклонил токен"
            log.warning("DLX: пробный перевод ответил HTTP %s", error.code)
            return "down"
        except (urllib.error.URLError, OSError, ValueError) as error:
            log.warning("DLX: пробный перевод не прошёл: %s", str(error)[:120])
            return "down"
        return "ready" if _answer_text(answer) else "upstream"

    def health(self, timeout: float = HEALTH_TIMEOUT) -> bool:
        """Готов ли сервис переводить / is the service ready to translate."""
        return self.probe(timeout) == "ready"

    def translate(self, text: str, source: str = "auto", target: str = "IT",
                  timeout: float = 8.0) -> str:
        """Перевести текст через локальный сервис / translate via the service."""
        if not self._alive():
            raise DlxError("локальный сервис не запущен")
        payload = {"text": text, "source_lang": source, "target_lang": target}
        try:
            answer = _http_post_json(self._url(), payload, self._auth(),
                                     timeout)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                log.warning("DLX: DeepL ограничил запросы (429) — уходим на откат")
                raise DlxError("DeepL ограничил запросы (429)") from error
            if error.code == 503:
                log.warning("DLX: DeepL не отвечает (503) — уходим на откат")
                raise DlxError("DeepL не отвечает (503)") from error
            if error.code == 413:
                log.warning("DLX: текст длиннее 1500 символов (413)")
                raise DlxError("текст длиннее 1500 символов") from error
            if error.code == 400:
                raise DlxError("сервис не принял язык перевода") from error
            log.warning("DLX: сервис ответил HTTP %s", error.code)
            raise DlxError(f"HTTP {error.code}") from error
        except (urllib.error.URLError, OSError) as error:
            log.warning("DLX: нет связи с локальным сервисом: %s", str(error)[:80])
            raise DlxError(f"нет связи с локальным сервисом: {str(error)[:60]}") from error
        except ValueError as error:
            log.warning("DLX: сервис ответил не JSON: %s", str(error)[:80])
            raise DlxError("сервис ответил не JSON") from error
        result = _answer_text(answer)
        if not result:
            reason = _answer_error(answer) or "пустой ответ"
            log.warning("DLX: %s", reason)
            raise DlxError(reason)
        return result

    # ------------------------------------------------------- установка и обновление
    def install(self, progress: Callable[[str], None] | None = None) -> bool:
        """Скачать сервис с GitHub (нужно согласие пользователя).

        Download the service from GitHub; the caller must have asked the user
        first. Returns True when the binary is in place.
        """
        # два одновременных скачивания писали один файл и портили его — отсюда
        # потом был WinError 193 «не является приложением Win32»
        # two downloads used to write one file and corrupt it, which later showed
        # up as WinError 193 "not a valid Win32 application"
        if not self._install_lock.acquire(timeout=1.0):
            log.info("DLX: установка уже идёт, ждать не буду")
            return self.installed()
        try:
            return self._install_locked(progress)
        finally:
            self._install_lock.release()

    def _install_locked(self, progress: Callable[[str], None] | None) -> bool:
        """Установка под блокировкой / the install itself, behind the lock."""
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            release = _http_get_json(RELEASE_API)
        except Exception as error:
            self._set_state("error", f"нет доступа к GitHub: {str(error)[:60]}")
            log.warning("DLX: не удалось получить список релизов: %s", error)
            return False
        version = str((release or {}).get("tag_name") or "").strip()
        url = _pick_asset((release or {}).get("assets") or [])
        if not url:
            self._set_state("error", "в релизе нет файла для Windows")
            log.warning("DLX: в релизе %s нет подходящего файла", version)
            return False
        if progress:
            progress(f"скачиваю {version or 'сервис'}…")
        # у каждого потока свой временный файл / every thread gets its own temp file
        temp = self.binary.with_name(
            f"{self.binary.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "RP-Chat-Overlay"})
            with urllib.request.urlopen(request, timeout=60) as answer, \
                    temp.open("wb") as out:
                while True:
                    chunk = answer.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
        except Exception as error:
            self._set_state("error", f"скачивание не удалось: {str(error)[:60]}")
            log.exception("DLX: скачивание не удалось")
            temp.unlink(missing_ok=True)
            return False
        if not _is_pe_file(temp) and sys.platform == "win32":
            self._set_state("error", "скачанный файл не похож на программу")
            temp.unlink(missing_ok=True)
            return False
        try:
            os.replace(temp, self.binary)
        except OSError as error:
            self._set_state("error", f"не удалось записать файл: {error}")
            return False
        self._fetch_license()
        write_json(self.dir / "version.json",
                   {"version": version, "installed": int(time.time())})
        log.info("DLX установлен: %s", version or "версия неизвестна")
        return True

    def _fetch_license(self) -> None:
        """Положить рядом лицензию MIT / keep the MIT license next to the binary."""
        target = self.dir / "LICENSE-DLX.txt"
        try:
            request = urllib.request.Request(LICENSE_URL,
                                             headers={"User-Agent": "RP-Chat-Overlay"})
            with urllib.request.urlopen(request, timeout=15) as answer:
                text = answer.read().decode("utf-8", "replace")
        except Exception:
            text = ("DLX — MIT License. Full text: " + LICENSE_URL + "\n")
        try:
            target.write_text(text, encoding="utf-8")
        except OSError:
            log.exception("DLX: не удалось записать лицензию")

    def check_update(self) -> str:
        """Версия новее установленной или пустая строка / a newer version or ""."""
        try:
            release = _http_get_json(RELEASE_API)
        except Exception as error:
            log.info("DLX: проверка обновлений не удалась: %s", str(error)[:80])
            return ""
        latest = str((release or {}).get("tag_name") or "").strip()
        if latest and latest != self.version():
            return latest
        return ""

    def uninstall(self) -> None:
        """Удалить сервис с диска / remove the service from disk."""
        self.stop()
        for path in (self.binary, self.dir / "version.json",
                     self.dir / "LICENSE-DLX.txt"):
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                log.exception("DLX: не удалось удалить %s", path)
        self._set_state("missing", "сервис удалён")


def _answer_text(answer: Any) -> str:
    """Достать перевод из ответа DLX / pull the translation out of the reply.

    Разные версии сервиса отвечают по-разному: строкой, объектом с «data»
    или объектом с «translations». Different service versions answer with a
    plain string, with «data» or with «translations».
    """
    if isinstance(answer, str):
        return answer.strip()
    if isinstance(answer, dict):
        data = answer.get("data")
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, list) and data:
            return str(data[0]).strip()
        items = answer.get("translations")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                return str(first.get("text") or "").strip()
            return str(first).strip()
    return ""


def _answer_error(answer: Any) -> str:
    """Код и текст ошибки из ответа / the error code and message."""
    if isinstance(answer, dict):
        code = answer.get("code")
        message = answer.get("message") or answer.get("error") or ""
        if message:
            return f"{message} (код {code})" if code else str(message)
    return ""


def _pick_asset(assets: list) -> str:
    """Выбрать файл для Windows x64 из релиза / pick the Windows x64 asset."""
    candidates = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").lower()
        url = str(asset.get("browser_download_url") or "")
        if not url or not name.endswith(".exe"):
            continue
        score = 0
        score += 3 if "windows" in name or "win" in name else 0
        score += 2 if ("amd64" in name or "x86_64" in name or "64" in name) else 0
        candidates.append((score, url))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: -item[0])
    return candidates[0][1]


def service_for(cfg: Mapping[str, Any], on_event: EventFn | None = None) -> DlxService:
    """Готовый сервис для текущих настроек / a service bound to the settings.

    Тестам и сборкам без Windows можно подменить команду через переменную
    окружения DLX_COMMAND. Tests and non-Windows builds may override the
    command line with the DLX_COMMAND environment variable.
    """
    command = None
    raw = os.environ.get("DLX_COMMAND", "").strip()
    if raw:
        command = raw.split("|")
    return DlxService(cfg, command=command, on_event=on_event)
