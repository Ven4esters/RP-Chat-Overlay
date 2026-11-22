"""Журнал ошибок: ловим всё, что обычно исчезает молча.

Error log: catches everything that usually disappears without a trace.

Зачем отдельный файл / why a separate file:
  * `logs/app.log` пишет ход работы, но падение внутри чужой библиотеки,
    ошибка в фоновом потоке или аварийное завершение процесса туда не попадают;
    `app.log` records the normal flow, but a crash inside a third-party library,
    an error in a background thread or an abnormal process exit never gets there;
  * здесь собраны четыре перехватчика: необработанные исключения, исключения
    потоков, сообщения Qt и `faulthandler` — он печатает стек даже тогда, когда
    процесс убивает сам себя (например, при вызове Qt не из главного потока).
    four hooks live here: unhandled exceptions, thread exceptions, Qt messages and
    `faulthandler`, which prints a stack even when the process kills itself
    (a widget created outside the main thread, for example).
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import traceback
from pathlib import Path

from app.config import LOGS, log

ERROR_PATH: Path = LOGS / "errors.log"  # только предупреждения и хуже / warnings and worse

_handle = None  # открытый файл для faulthandler / the file kept open for faulthandler
_installed = False


def _open() -> None:
    """Открывает файл журнала ошибок и оставляет его открытым.

    Opens the error log and keeps the handle alive: faulthandler writes into a
    raw file descriptor and cannot reopen it later.
    """
    global _handle
    if _handle is not None:
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    # Дескриптор нужен faulthandler до самого выхода из программы — noqa ниже.
    # The descriptor is needed by faulthandler until the process exits.
    _handle = open(ERROR_PATH, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    _handle.write(
        f"\n=== {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} "
        f"старт журнала ошибок / error log started ===\n"
    )
    _handle.flush()


def _writer(level: str, text: str) -> None:
    """Пишет строку в файл ошибок, не заходя в logging (чтобы не уйти в рекурсию).

    Writes a line straight into the error file, bypassing logging so that a
    message handler cannot recurse into itself.
    """
    _open()
    try:
        _handle.write(f"{level}: {text}\n")
        _handle.flush()
    except (OSError, ValueError):
        pass


def _excepthook(exc_type, exc, tb) -> None:
    """Необработанная ошибка главного потока / an unhandled exception in the main thread."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log.critical("Необработанная ошибка / unhandled error\n%s", text)


def _threadhook(args) -> None:
    """Ошибка в фоновом потоке / an error inside a background thread."""
    name = getattr(args.thread, "name", "?") if args.thread else "?"
    text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    log.critical("Ошибка в потоке %s / error in thread %s\n%s", name, name, text)


def _unraisable(args) -> None:
    """Исключение, которое Python не может поднять / an exception nobody can raise."""
    text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    log.error("Необрабатываемое исключение / unraisable exception\n%s", text)


def _qt_handler(mode, context, message) -> None:
    """Сообщения самого Qt: предупреждения, критические и фатальные.

    Qt's own messages: warnings, criticals and fatals. A fatal one is usually the
    last thing written before a silent crash, so it matters most.
    """
    text = f"{message}"
    if context and getattr(context, "file", None):
        text += f"  ({context.file}:{context.line})"
    # имена режимов приходят с префиксом: QtWarningMsg, QtFatalMsg и так далее
    # mode names arrive with a prefix: QtWarningMsg, QtFatalMsg and so on
    name = getattr(mode, "name", str(mode)).replace("Qt", "")
    level = {"WarningMsg": "WARNING", "CriticalMsg": "CRITICAL", "FatalMsg": "FATAL"}.get(name)
    if level:
        _writer(f"QT-{level}", text)
        if level != "WARNING":
            log.error("Qt: %s", text)


def install() -> None:
    """Включает все перехватчики; повторный вызов ничего не делает.

    Enables every hook; calling it twice does nothing.
    """
    global _installed
    if _installed:
        return
    _installed = True
    _open()

    # 1. аварийные падения: segfault, abort() внутри Qt или библиотеки
    #    hard crashes: a segfault or an abort() inside Qt or a library
    try:
        faulthandler.enable(file=_handle, all_threads=True)
    except (OSError, ValueError):
        pass

    # 2. необработанные исключения и потоки / unhandled exceptions and threads
    sys.excepthook = _excepthook
    threading.excepthook = _threadhook
    sys.unraisablehook = _unraisable

    # 3. отдельный файл для предупреждений и ошибок — рядом с app.log
    #    a separate file for warnings and errors, next to app.log
    handler = logging.FileHandler(ERROR_PATH, encoding="utf-8")
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    # 4. сообщения Qt (импорт внутри: журнал нужен и без PySide6)
    #    Qt messages (imported here so the log works without PySide6 too)
    try:
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(_qt_handler)
    except Exception:  # нет PySide6 или консольная сборка
        pass

    _writer("INFO", f"перехватчики включены, файл {ERROR_PATH}")


_beat = {"time": 0.0}  # последний отклик главного потока / last heartbeat


def _beat_tick() -> None:
    """Отметка «главный поток жив» / a heartbeat mark from the main thread."""
    import time as _time

    _beat["time"] = _time.monotonic()


def watch_main_thread(timeout: float = 20.0, parent=None):
    """Следит, что главный поток отвечает; при зависании пишет стеки всех потоков.

    Watches that the main thread is responsive. When it stalls, every thread stack
    is written to the error log: a freeze that leaves no trace is the hardest kind
    of bug to report, and this turns it into a readable dump.
    """
    import time as _time

    try:
        from PySide6.QtCore import QTimer
    except Exception:
        return None
    _beat["time"] = _time.monotonic()
    timer = QTimer(parent)
    timer.setInterval(500)
    timer.timeout.connect(_beat_tick)
    timer.start()

    def watch() -> None:
        reported = 0.0
        while True:
            _time.sleep(1.0)
            stall = _time.monotonic() - _beat["time"]
            if stall > timeout and stall - reported > timeout:
                reported = stall
                _writer(
                    "HANG",
                    f"главный поток не отвечает {stall:.0f} с / main thread stalled, stacks below",
                )
                try:
                    faulthandler.dump_traceback(file=_handle, all_threads=True)
                except (OSError, ValueError):
                    pass
                log.error("Главный поток не отвечает %.0f с — стеки в %s", stall, ERROR_PATH)

    threading.Thread(target=watch, name="hang-watch", daemon=True).start()
    return timer


def tail(lines: int = 40) -> str:
    """Последние строки журнала ошибок — для сообщения в интерфейсе.

    The last lines of the error log, handy for an interface message.
    """
    try:
        content = ERROR_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])
