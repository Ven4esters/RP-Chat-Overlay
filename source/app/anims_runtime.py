"""Animation matching orchestration and playback queue runtime."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable, Iterable, Mapping

from app.config import log
from app.usage_report import measure_call
from app.anims_rules import (
    ANIM_EXTRA_MS,
    MAX_EXTRA_MS,
    MAX_QUEUE,
    Choice,
    Context,
    Rule,
    _same_rule,
    rules_from_cfg,
    select_spans,
)


# ------------------------------------------------------------------ разбор
@measure_call("animation.plan")
def plan(
    rules: Iterable["Rule"], text: str, ctx: "Context | None" = None
) -> list[tuple[int, int, "Rule", str]]:
    """Что сыграет и в каком порядке: (место, номер правила, правило, текст).

    What plays, and in which order: (position, rule number, rule, text).

    Это единственное место, где решается судьба вложенных ключей: «сел» и «сел
    откинувшись» — разные правила, и решать приходится сразу за оба. Порядок —
    по месту в сообщении, при равных местах — по таблице правил.
    This is the only place where nested keywords are settled: «сел» and «сел
    откинувшись» are separate rules, so the decision has to cover both at once.
    The order follows the message, ties follow the rule table.
    """
    table = list(rules)
    ctx = ctx or Context()
    candidates: list[tuple[int, int, int, int, str]] = []
    for index, rule in enumerate(table):
        for begin, end, order in rule.candidates(text, ctx):
            candidates.append((begin, end, index, order, text[begin:end]))
    if not candidates:
        return []
    picked = select_spans(
        (begin, end, (index, order)) for begin, end, index, order, _ in candidates
    )
    chosen = {(begin, end) for begin, end, _ in picked}
    # что не сыграло и почему — видно в журнале
    # what did not play, and why, is visible in the log
    for begin, end, index, _order, _form in candidates:
        if (begin, end) in chosen:
            continue
        if any(
            other_begin <= begin and end <= other_end and (other_end - other_begin) > (end - begin)
            for other_begin, other_end, _label in picked
        ):
            log.info("Анимации: короткое вложенное совпадение пропущено (правило=%d)", index + 1)
    # одно правило в одном месте срабатывает один раз, а разные правила на одном
    # и том же слове — оба, как было и раньше
    # a rule fires once at one place; different rules on the same word both fire,
    # exactly as before
    per_rule_span: dict[tuple[int, int, int], None] = {}
    for begin, end, (index, _order) in picked:
        per_rule_span[(begin, end, index)] = None
    result = [
        (begin, index, table[index], text[begin:end])
        for begin, end, index in sorted(per_rule_span, key=lambda item: item[:2])
    ]
    for index, _rule in enumerate(table):
        forms: list[str] = []
        played = 0
        for begin, end, hit_index, _order, form in candidates:
            if hit_index != index:
                continue
            if form not in forms:
                forms.append(form)
            if (begin, end) in chosen:
                played += 1
        if not forms:
            continue
        # одно срабатывание на каждое ключевое слово правила: разные ключи
        # играют подряд, повтор того же слова — только раз
        # one hit per keyword of the rule: different keywords play in turn, a
        # repeated word plays once
        log.info(
            "Анимации: проверка правила %d — кандидатов: %d, выбрано: %d",
            index + 1,
            len(forms),
            played,
        )
    return result


# ------------------------------------------------------------------ исполнитель
class Runner:
    """Очередь анимаций: `/anim` -> пауза -> `/sa`, при зацикливании по кругу.

    The animation queue: `/anim` -> wait -> `/sa`, repeating while looping.

    send     функция отправки команды в игру: str -> (успех, сообщение);
             a function that sends a command to the game: str -> (ok, message)
    on_event колбэк (вид, текст): «error», «playing», «done», «stopped»;
             a callback (kind, text) for the interface and the player
    """

    def __init__(
        self,
        cfg: Mapping[str, Any] | None = None,
        send: Callable[[str], tuple[bool, str]] | None = None,
        on_event: Callable[[str, str], None] | None = None,
        equivalent: Callable[[str], str] | None = None,
        press_key: Callable[[str], tuple[bool, str]] | None = None,
        text_keys: Callable[[str], list[tuple[int, int, str]]] | None = None,
        chooser: Callable[["Rule"], "Choice | None"] | None = None,
    ) -> None:
        """equivalent — «фраза -> ключ словаря» для слов-синонимов.

        equivalent is the "phrase -> glossary key" function used for synonyms.

        text_keys — «текст -> [(начало, конец, ключ)]»: какие фразы словаря есть
        в сообщении. Без неё синонимами считаются только отдельные слова.
        text_keys tells which glossary phrases sit in the text; without it only
        single words count as synonyms.

        press_key — нажать клавишу в игре (симуляция нажатия) для остановки
        анимации клавишей вместо команды `/sa`.
        press_key presses a key in the game (a simulated press) so an animation
        can be stopped by a key instead of the /sa command.

        chooser — спросить игрока, какой из вариантов играть. Вызывается из
        потока очереди и должен вернуть выбранный ``Choice`` или None, если
        игрок отказался (или оверлей показать не удалось) — тогда правило
        пропускается целиком. Без неё правило с вариантами играет первый.
        chooser asks the player which variant to play. It is called from the
        queue thread and must return the chosen ``Choice``, or None when the
        player backed out (or the overlay could not be shown) — the rule is then
        skipped entirely. Without it a rule with variants plays the first one.
        """
        self.cfg: Mapping[str, Any] = cfg or {}
        self.send = send or (lambda command: (False, "отправка недоступна"))
        self.on_event = on_event
        self.equivalent = equivalent
        self.press_key = press_key
        self.text_keys = text_keys
        self.chooser = chooser
        self._rules: list[Rule] = rules_from_cfg(self.cfg)
        self._queue: deque[Rule] = deque()
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._done = threading.Event()
        self._end_at = 0.0  # конец проигрывания, monotonic
        # Смена анимации на ходу: окно выбора остаётся открытым, и новый выбор
        # приходит сюда, а не в очередь.
        # Swapping the animation on the fly: the chooser stays open, and a new pick
        # arrives here instead of the queue.
        self._swap_choice = None  # какой вариант просят играть
        self._play_token = 0  # номер текущего захода правила
        self._quiet_off = False  # про выключенный модуль пишем раз
        self._stop_run = threading.Event()  # прервать текущий цикл / abort the run
        self._current: Rule | None = None
        self._last_error = ""
        self._last_trigger = ""
        self._reset_pending = False  # после остановки игроком отправить /sa
        # send /sa after a stop by the player
        # Режим «В машине»: пока он включён, ни одна команда в игру не уходит.
        # Признак приходит снаружи (галочка в настройках, пункт меню трея),
        # потому что состояние игры программе недоступно.
        # The "In a vehicle" mode: while it is on, no command leaves for the game.
        # The flag comes from outside (a checkbox in the settings, a tray menu
        # item), because the game state is not available to the program.
        self._vehicle = False
        self._vehicle_note = ""

    # ------------------------------------------------------------ настройки
    def reload(self, cfg: Mapping[str, Any]) -> None:
        """Перечитать правила из настроек / reload the rules from the settings."""
        self.cfg = cfg or {}
        with self._lock:
            self._rules = rules_from_cfg(self.cfg)
        if not self.enabled():
            self.clear("модуль выключен")

    def enabled(self) -> bool:
        """Включён ли модуль / is the module switched on."""
        return bool(self.cfg.get("anims_enabled", False))

    # ------------------------------------------------------ режим «В машине»
    def vehicle(self) -> bool:
        """Включён ли режим «В машине» / is the "In a vehicle" mode on."""
        return bool(self._vehicle)

    def set_vehicle(self, on: bool, reason: str = "") -> bool:
        """Включить или выключить режим «В машине» / turn the vehicle mode on or off.

        Включение — это команда «больше ничего не запускать», поэтому оно сразу
        делает три вещи: снимает очередь, гасит зацикливание и отправляет ровно
        один `/sa`, чтобы в игре не осталось кривой позы. Дальше — тишина: пока
        режим включён, ни `/anim`, ни `/sa` в игру не уходят.
        Второй `/sa` здесь был бы вреден: первый же и убирает анимацию, а лишняя
        команда в машине снова дёргает персонажа.
        Turning it on means "start nothing else", so it does three things at
        once: drops the queue, breaks the loop and sends exactly one `/sa` so that
        no crooked pose is left in the game. After that comes silence: while the
        mode is on, neither `/anim` nor `/sa` leaves for the game.
        A second `/sa` would only hurt here: the first one already removes the
        animation, and an extra command in a vehicle jerks the character again.

        ``reason`` — что написать игроку и в журнал; по умолчанию «в машине».
        ``reason`` is shown to the player and written to the log; "in a vehicle"
        by default.
        """
        reason = reason or "в машине"
        was = bool(self._vehicle)
        self._vehicle = bool(on)
        self._vehicle_note = reason if on else ""
        if not on:
            # Режим выключили: очередь, снятая при включении, не возвращается —
            # сообщения, которые её наполнили, уже старые. Игрок напишет новое.
            # The mode is off: the queue dropped on the way in does not come
            # back — the messages that filled it are stale by now.
            if was:
                log.info("Анимации: режим «в машине» выключен")
            self._emit("vehicle", "режим «в машине» выключен")
            return True
        if was:
            # повторное включение ничего не отправляет: режим уже держит тишину
            # turning it on again sends nothing: the mode already keeps silence
            return True
        log.info("Анимации: режим «в машине» включён — анимации остановлены")
        self._drop_choice_window(close=True)
        with self._cv:
            dropped = [rule.name for rule in self._queue]
            self._queue.clear()
            self._stop_run.set()
            self._cv.notify_all()
        if dropped:
            log.info("Анимации: очередь снята (%s)", ", ".join("/anim " + name for name in dropped))
        current = self._current
        if current is not None:
            # ровно одна остановка, и только если что-то играло
            # exactly one stop, and only when something was playing
            try:
                # единственная команда, которой режим пропускает: она и убирает
                # анимацию, из-за которой персонаж в машине сидит криво
                # the only command the mode lets through: it removes the
                # animation that makes the character sit crooked in a vehicle
                self._send("/sa", current, quiet=True, force=True)
            except Exception:
                log.exception("Анимации: не удалось отправить /sa при входе в машину")
            self._emit("stopped", "остановлено перед машиной")
        self._emit("vehicle", "режим «в машине» включён")
        return True

    def guard_quiet(self) -> bool:
        """Пускать ли текущее действие в игру / may the current action reach the game.

        Единственное место, где решается «молчать или отправлять»: пока режим
        включён, ни одна команда не уходит. Ошибку пишем один раз, чтобы журнал
        не забивался одинаковыми строками.
        The only place that decides "silent or send": while the mode is on no
        command leaves. The log line is written once, so it does not fill up.
        """
        if not self._vehicle:
            return True
        if not self._quiet_off:
            self._quiet_off = True
            log.info("Анимации: режим «в машине» — команды в игру не отправляются")
        return False

    def rules(self) -> list[Rule]:
        with self._lock:
            return list(self._rules)

    # ------------------------------------------------------------ сообщения
    def feed(self, text: str) -> list[Rule]:
        """Проверить сообщение и поставить срабатывания в очередь.

        Check a message and queue every hit.

        Порядок — как в самом сообщении: сначала то, что игрок написал раньше.
        Правило играет в сообщении **один раз**, даже если ключевое слово
        повторилось: «чёрт, чёрт» даёт одну анимацию, а место в очереди берётся
        по первому совпадению. Слова-синонимы, которые переводятся так же, как
        ключевое, тоже срабатывают — если передана функция ``equivalent``.
        The order follows the message itself: whatever was written first plays
        first. A rule plays **once per message** even when its keyword repeats:
        «чёрт, чёрт» gives one animation, and the place in the queue is taken from
        the first match. Synonyms that translate like the keyword fire too when an
        ``equivalent`` function is provided.
        """
        if not self.enabled():
            if not self._quiet_off:
                self._quiet_off = True
                log.info("Анимации: модуль выключен — правила не проверяются")
            return []
        if self._vehicle:
            # В машине ни правила не проверяем, ни очередь не трогаем: игрок
            # не должен удивиться, когда после выхода из машины вдруг сыграет
            # то, что он написал десять минут назад на ходу.
            # In a vehicle neither the rules nor the queue are touched: the
            # player must not be surprised by something written ten minutes ago
            # suddenly playing after getting out.
            if not self._quiet_off:
                self._quiet_off = True
                log.info("Анимации: режим «в машине» — правила не проверяются")
            return []
        if not (text or "").strip():
            return []
        self._quiet_off = False  # снова говорим, если что-то не так
        ctx = Context(
            equivalent=self.equivalent, text_keys=self.text_keys, negation=self.negation()
        )
        rules = [rule for rule in self.rules() if rule.ready()]
        hits = plan(rules, text, ctx)
        log.info(
            "Анимации: в очередь %s", " -> ".join("/anim " + rule.name for _, _, rule, _ in hits)
        )
        for _, _, rule, _ in hits:
            # Меню этого правила ещё висит в очереди выбора — возвращаем его,
            # а не открываем второе такое же: игрок как раз хочет поменять
            # анимацию по этому ключу.
            # This rule's menu is still waiting in the choice queue: it is brought
            # back instead of opening a second one — the player wants to change the
            # animation for that keyword.
            focus = getattr(self.chooser, "focus_menu_for", None)
            if callable(focus) and rule.needs_choice():
                try:
                    if focus(rule):
                        log.info("Анимации: меню выбора повторно открыто из очереди")
                        continue
                except Exception:
                    log.exception("Анимации: не удалось вернуть меню выбора")
            self._enqueue(rule)
        return [rule for _, _, rule, _ in hits]

    def _enqueue(self, rule: Rule) -> None:
        # Страховка: в машине очередь не наполняется даже в обход feed.
        # A safeguard: in a vehicle the queue does not fill up even around feed.
        if self._vehicle:
            return
        copy = Rule.from_dict(rule.to_dict())  # снимок на момент срабатывания
        with self._cv:
            if len(self._queue) >= MAX_QUEUE:
                log.warning("Анимации: очередь переполнена, «%s» отброшено", rule.name)
                self._last_error = "очередь переполнена"
                return
            self._queue.append(copy)
            self._last_trigger = rule.keywords
            self._ensure_thread()
            self._cv.notify_all()

    # ----------------------------------------------------------- управление
    def stop_user(self) -> bool:
        """Остановить текущую анимацию (горячая клавиша), очередь не трогать.

        Stop the animation playing right now (the stop hotkey) and keep the queue.
        Очередь остаётся: остальные срабатывания пришли из того же сообщения и
        должны сыграть. Снять очередь целиком может только полная остановка —
        ``stop()`` или ``clear()``.
        The queue stays: the other hits came from the same message and must still
        play. Only a full stop — ``stop()`` or ``clear()`` — drops it.
        """
        self._reset_pending = True
        # Меню остановленного правила больше не живое: следующий тот же ключ
        # должен открыть свежее меню, а не вернуть старое с отмеченным вариантом.
        # Само окно остаётся на экране — игрок может выбрать другой вариант.
        # The stopped rule's menu is no longer live: the next hit of the same
        # keyword must open a fresh menu, not bring back the old one with a marked
        # variant. The window itself stays — the player may pick another variant.
        self._chooser_stopped(self._current)
        self._drop_choice_window()
        with self._cv:
            queued = len(self._queue)
            if not self._current and not queued:
                return False
            self._stop_run.set()
            self._cv.notify_all()
        log.info("Анимации: остановлено игроком, в очереди остаётся: %d", queued)
        self._emit("stopped", "остановлено игроком")
        return True

    def stop(self, reason: str = "") -> bool:
        """Прервать текущий цикл и очистить очередь / abort the run and the queue."""
        stopped = bool(self._current) or bool(self._queue)
        # полная остановка убирает окно совсем; клавиша остановки его оставляет
        # a full stop removes the window for good; the stop key keeps it
        self._drop_choice_window(close=True)
        if reason and reason != "остановлено игроком":
            self._reset_pending = False
        with self._cv:
            dropped = [rule.name for rule in self._queue]
            self._queue.clear()
            self._stop_run.set()
            self._cv.notify_all()
        if dropped:
            # очередь снята целиком — в журнале видно, что именно не сыграет
            # the whole queue is dropped — the log shows what will not play
            log.info("Анимации: очередь снята (%s)", ", ".join("/anim " + name for name in dropped))
        if stopped:
            log.info("Анимации: %s", reason or "остановлено")
            self._emit("stopped", reason or "остановлено")
        return stopped

    def clear(self, reason: str = "") -> None:
        """Полная остановка: очередь, текущая анимация и рабочий поток.

        A full stop: the queue, the running animation and the worker thread.
        """
        self.stop(reason)
        self._done.set()
        with self._cv:
            self._cv.notify_all()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        self._thread = None
        self._done.clear()

    def shutdown(self) -> None:
        """Гашение при выходе программы / the shutdown hook."""
        try:
            self.clear("программа закрывается")
        except Exception:
            log.exception("Анимации: сбой при остановке")

    # --------------------------------------------------------------- состояние
    def state(self) -> dict[str, Any]:
        """Что показать в настройках / what the settings page shows."""
        with self._lock:
            return {
                "enabled": self.enabled(),
                "rules": len(self._rules),
                "current": self._current.name if self._current else "",
                "loop": bool(self._current and self._current.loop),
                "queued": len(self._queue),
                "error": self._last_error,
                "trigger": self._last_trigger,
                "vehicle": bool(self._vehicle),
            }

    def _emit(self, kind: str, text: str) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(kind, text)
        except Exception:
            log.exception("Анимации: колбэк состояния упал")

    # ------------------------------------------------------------ исполнение
    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._done.clear()
        self._thread = threading.Thread(target=self._loop, name="anims", daemon=True)
        self._thread.start()

    def _next(self) -> Rule | None:
        with self._cv:
            while not self._queue and not self._done.is_set():
                self._cv.wait(0.25)
            if self._done.is_set() or not self._queue:
                return None
            return self._queue.popleft()

    def _loop(self) -> None:
        """Очередь: анимация проигрывает своё время, хвост — и следующая.

        The queue: an animation plays its own time, then the tail, then the next.
        Хвост (``anim_extra_ms``, по умолчанию 50 мс) отмеряется от конца
        проигрывания: 1500 мс анимации + 50 мс — играет следующая. Он же даёт
        игре закрыть чат после остановки и серверу принять новую команду.
        The tail (``anim_extra_ms``, 50 ms by default) starts at the end of the
        play: 1500 ms of animation + 50 ms — the next one plays. It also gives
        the game time to close its chat after the stop and the server time to
        take the new command.
        """
        while not self._done.is_set():
            rule = self._next()
            if rule is None:
                return
            if self._vehicle:
                # Режим включили, пока правило ждало очереди: не играем.
                # The mode was turned on while the rule waited: do not play it.
                log.info("Анимации: «%s» снято — включён режим «в машине»", rule.name)
                with self._lock:
                    self._current = None
                continue
            try:
                self._play(rule)
            except Exception:
                log.exception("Анимации: сбой при проигрывании «%s»", rule.name)
                self._last_error = "сбой при отправке"
                self._end_at = time.monotonic()
            finally:
                with self._lock:
                    self._current = None
            extra = self.extra()
            if extra:
                left = self._end_at + extra - time.monotonic()
                if left > 0:
                    # флаг остановки от прошлой анимации сюда не относится
                    # a stop flag left over from the previous animation is not
                    # about this one
                    self._stop_run.clear()
                    if self._stop_run.wait(left):
                        # остановили во время хвоста: следующую не играем
                        # stopped during the tail: the next one is dropped
                        self._stop_run.clear()

    def negation(self) -> bool:
        """Не срабатывать на отрицание? / should negation silence a rule."""
        return bool(self.cfg.get("anim_skip_negation", True))

    def extra(self) -> float:
        """Хвост после анимации в секундах / the tail after an animation.

        Сколько добавить к времени проигрывания, прежде чем запускать следующую
        анимацию из очереди: 1500 мс анимации + 50 мс хвоста — играет следующая.
        Настройка ``anim_extra_ms`` (по умолчанию ``ANIM_EXTRA_MS``); старое поле
        ``anim_gap_ms`` читается как она же, чтобы настройки не потерялись.
        How much to add to the play time before the next animation starts:
        1500 ms of animation + 50 ms of tail — the next one plays. The setting is
        ``anim_extra_ms`` (``ANIM_EXTRA_MS`` by default); the old ``anim_gap_ms``
        is read as the same value so the settings are not lost.
        """
        raw = self.cfg.get("anim_extra_ms")
        if raw is None:
            raw = self.cfg.get("anim_gap_ms", ANIM_EXTRA_MS)
        try:
            ms = int(raw)
        except (TypeError, ValueError):
            ms = ANIM_EXTRA_MS
        return min(MAX_EXTRA_MS, max(0, ms)) / 1000.0

    def stop_methods(self) -> tuple[bool, bool]:
        """Как останавливать анимацию: (командой /sa, клавишей).

        How to stop an animation: (with the /sa command, with the key).
        """
        by_sa = bool(self.cfg.get("anim_stop_by_sa", True))
        by_key = bool(self.cfg.get("anim_stop_by_key", False))
        return by_sa, by_key

    def _stop_animation(self, rule: Rule) -> None:
        """Остановить анимацию выбранными способами / stop it the chosen ways.

        Настройки дают два независимых способа: команда `/sa` и симуляция
        нажатия клавиши (по умолчанию F — та же, что прекращает анимацию в игре).
        Включены оба — применяются оба; выключены оба — анимация не
        останавливается совсем.
        The settings offer two independent ways: the `/sa` command and a
        simulated key press (F by default, the key the game itself uses). Both on
        means both are used; both off means the animation is not stopped at all.
        """
        if not self.guard_quiet():
            return
        by_sa, by_key = self.stop_methods()
        if by_sa:
            self._send("/sa", rule, quiet=True)
        if by_key:
            spec = str(self.cfg.get("anim_stop_key", "f") or "f")
            if self.press_key is None:
                log.warning("Анимации: нажатие клавиши «%s» недоступно", spec)
                return
            try:
                ok, message = self.press_key(spec)
            except Exception as error:
                log.exception("Анимации: не удалось нажать «%s»", spec)
                ok, message = False, str(error)[:120]
            if ok:
                log.info("Анимации: нажата клавиша «%s»", spec)
            else:
                self._last_error = message or "клавиша не нажалась"
                log.warning("Анимации: клавиша «%s» не нажалась — %s", spec, self._last_error)

    def _play(self, rule: Rule) -> None:
        """Один заход правила: /anim -> пауза -> остановка или снова /anim.

        One rule run: /anim -> wait -> stop, or /anim again while looping.

        Длительность 0 мс означает «не останавливать»: уходит только `/anim`.
        A duration of 0 ms means "never stop": only `/anim` is sent.
        """
        self._stop_run.clear()
        with self._lock:
            self._current = rule
            self._play_token += 1
            token = self._play_token
            self._swap_choice = None
        # выбор варианта — до первого /anim: пока игрок думает, в игре ничего
        # не играет, и очередь стоит. Окно после выбора не закрывается, и выбор
        # другого варианта меняет анимацию на ходу.
        # the variant is chosen before the first /anim: nothing plays in the game
        # while the player picks, and the queue waits. The window stays open after
        # the pick, and picking another variant swaps the animation on the fly.
        variant = self._choose(rule, token)
        if variant is None:
            # игрок отказался или оверлей не показать: правило пропускаем целиком,
            # иначе в чат уйдёт не то, что он ждал
            # the player backed out or the overlay could not be shown: the whole
            # rule is skipped, otherwise the game plays what he did not pick
            self._end_at = time.monotonic()
            self._withdraw_choice(token)
            return
        self._emit("playing", variant.label() if rule.needs_choice() else rule.name)
        # время проигрывания считается от отправки `/anim`: сама отправка тоже
        # занимает время (фокус в игру, чат, вставка, Enter), и оно входит в
        # длительность, иначе каждая пауза незаметно удлинялась бы на полсекунды
        # the play time counts from the `/anim` send: the send itself takes time
        # (focus, game chat, paste, Enter), and it belongs to the duration —
        # otherwise every pause would quietly grow by half a second
        started = time.monotonic()
        if not self._send(f"/anim {variant.name}", rule):
            self._end_at = started
            return
        if rule.duration_ms <= 0:
            # 0 мс: анимацию не останавливаем — ни /sa, ни клавишей
            # 0 ms: the animation is not stopped at all
            self._end_at = started
            self._emit("done", variant.name)
            return
        deadline = started + rule.duration_ms / 1000.0
        while True:
            # Смена варианта проверяется ДО решения о конце: за время ожидания
            # игрок мог нажать другой вариант, и тогда правило не заканчивается,
            # а играет выбранное — при зацикливании и без него одинаково.
            # The swap is checked BEFORE deciding the run is over: while waiting the
            # player may have picked another variant, and then the rule does not
            # end but plays the pick — with looping and without it alike.
            swapped = self._take_swap(token)
            if swapped is not None and swapped.name != variant.name:
                log.info("Анимации: смена варианта %s -> %s", variant.name, swapped.name)
                self._stop_animation(rule)
                variant = swapped
                self._emit("playing", variant.label())
                started = time.monotonic()
                if not self._send(f"/anim {variant.name}", rule):
                    self._end_at = started
                    return
                if rule.duration_ms <= 0:
                    self._end_at = started
                    self._emit("done", variant.name)
                    return
                deadline = started + rule.duration_ms / 1000.0
                continue
            if time.monotonic() < deadline:
                # Ждём короткими шагами, чтобы не проспать смену варианта.
                # Wait in short steps so a variant swap is not slept through.
                left = deadline - time.monotonic()
                if self._stop_run.wait(min(left, 0.08)):
                    # анимацию остановили клавишей игрока: гасим её выбранным
                    # способом
                    # the player stopped the animation: put it out the chosen way
                    if self._reset_pending:
                        self._reset_pending = False
                        self._stop_animation(rule)
                    self._end_at = time.monotonic()
                    self._withdraw_choice(token)
                    self._notify_rule_done(rule)
                    return
                continue
            if rule.loop:
                # при зацикливании остановки нет: анимация просто запускается
                # снова по таймеру, ровно через свою длительность
                # with looping on nothing stops: the animation simply starts
                # again by the timer, exactly one duration later
                deadline += rule.duration_ms / 1000.0
                if not self._send(f"/anim {variant.name}", rule, quiet=True):
                    self._end_at = deadline
                    return
                continue
            # без зацикливания пора останавливать — так, как выбрано в настройках
            # without looping it is time to stop, the way the settings say
            self._stop_animation(rule)
            # следующая анимация пойдёт через хвост после КОНЦА проигрывания, а
            # потраченное на остановку время из этого хвоста вычитается
            # the next animation starts one tail after the END of the play, and
            # the time spent stopping is taken out of that tail
            self._end_at = deadline
            # подписку не снимаем: меню ещё висит, и игрок может поменять
            # анимацию — тогда она сыграет заново (push_swap)
            # the subscription stays: the menu is still up, and the player may swap
            # the animation — then it plays again (push_swap)
            self._notify_rule_done(rule)
            self._emit("done", variant.name)
            return

    def _choose(self, rule: Rule, token: int = 0) -> "Choice | None":
        """Какой вариант играть / which variant to play.

        Три случая:
        Three cases:

        * вариантов нет или он один — играем его, оверлей не нужен;
          no variants or just one — it plays, no overlay needed;
        * вариантов два и больше, но спросить некого — играем первый, о чём
          честно пишем в журнал;
          two or more variants but nobody to ask — the first plays, and the log
          says so honestly;
        * есть ``chooser`` — спрашиваем игрока; None от него означает отказ, и
          тогда правило пропускается.
          a ``chooser`` is set — the player is asked; None means he backed out and
          the rule is skipped.
        """
        variants = rule.variant_list()
        if not variants:
            log.warning(
                "Анимации: у правила «%s» нет ни названия, ни вариантов", rule.keywords[:40]
            )
            return None
        if not rule.needs_choice():
            return variants[0]
        if self.chooser is None:
            log.warning(
                "Анимации: у правила «%s» %d варианта(ов), но выбрать негде — играю первый (%s)",
                rule.keywords[:40],
                len(variants),
                variants[0].name,
            )
            return variants[0]

        # выбор блокирует очередь: пока оверлей открыт, следующее правило ждёт
        # the choice blocks the queue: while the overlay is open the next rule
        # waits
        # Окно выбора не закрывается после ответа: игрок может передумать и
        # нажать другой вариант, и тогда анимация меняется на ходу.
        # The chooser does not close after the answer: the player may change his
        # mind and press another variant, and then the animation swaps on the fly.
        def on_change(choice):
            # Правило уже не играет — меню всё ещё открыто, и выбор должен
            # сыграть заново, а не пропасть. Это бывает в трёх случаях: правило
            # доиграло само, его остановил игрок (F) или очередь ушла дальше и
            # текущим стало другое правило.
            # The rule is not playing any more — the menu is still up and the pick
            # must replay instead of vanishing. That happens in three cases: the
            # rule ended by itself, the player stopped it (F), or the queue moved
            # on and another rule is current now.
            current = self._current
            if (
                (token and token != self._play_token)
                or current is None
                or not _same_rule(current, rule)
            ):
                self.push_swap(rule, choice)
                return
            with self._lock:
                self._swap_choice = choice

        attach = getattr(self.chooser, "attach", None)
        if callable(attach):
            # меню запоминает, чем сыграть выбор после конца правила
            # the menu remembers what to play a pick with after the rule ends
            attach(rule, lambda choice: self.push_swap(rule, choice))
        try:
            try:
                picked = self.chooser(rule, on_change=on_change)
            except TypeError:
                # заглушка без второго аргумента — обычная функция
                # a stub without the second argument is a plain function
                picked = self.chooser(rule)
        except Exception:
            log.exception("Анимации: выбор варианта не удался")
            return variants[0]
        if picked is None:
            log.info("Анимации: выбор варианта отменён — правило пропущено")
            return None
        log.info("Анимации: выбран вариант /anim %s", picked.name)
        return picked

    def _notify_rule_done(self, rule: "Rule | None" = None) -> None:
        """Сказать окну выбора, что правило доиграло.

        Tell the chooser window that the rule has finished.

        Окно остаётся открытым (закрывает его только игрок), но пометку «играет»
        снимаем: анимация больше не идёт.
        The window stays open (only the player closes it), but the "playing" mark
        is cleared: the animation is not running any more.
        """
        finished = getattr(self.chooser, "rule_finished", None)
        if callable(finished):
            try:
                try:
                    finished(rule)
                except TypeError:
                    # заглушка без параметра / a stub without the parameter
                    finished()
            except Exception:
                log.exception("Анимации: не удалось снять пометку в окне выбора")

    def push_swap(self, rule, choice) -> bool:
        """Меню открыто, а его правило уже доиграло: сыграть выбор заново.

        The menu is still open but its rule has finished: play the pick again.

        Иначе выбор по первому ключу пропадал бы, как только доиграет его
        анимация, — а игрок как раз может вернуться к нему и передумать.
        ``choice is None`` означает «закрыть»: поставленная в очередь анимация
        этого правила снимается, если ещё не началась.
        Otherwise a pick for the first keyword would be lost the moment its
        animation ends — while the player may well come back and change his mind.
        ``choice is None`` means "close": a queued animation of that rule is
        dropped if it has not started yet.
        """
        if choice is None:
            with self._cv:
                self._queue = deque(item for item in self._queue if not _same_rule(item, rule))
                if self._current is not None and _same_rule(self._current, rule):
                    self._stop_run.set()
                self._cv.notify_all()
            return True
        with self._cv:
            self._queue = deque(item for item in self._queue if not _same_rule(item, rule))
            copy = Rule.from_dict(rule.to_dict())
            copy.choices = [choice]
            copy.name = choice.name
            self._queue.appendleft(copy)
            self._ensure_thread()
            self._cv.notify_all()
        log.info("Анимации: выбор /anim %s играет заново", choice.name)
        return True

    def _take_swap(self, token: int) -> "Choice | None":
        """Забрать запрошенную смену варианта для этого захода правила.

        Take the requested variant swap for this rule run.
        """
        with self._lock:
            if token != self._play_token:
                return None
            choice, self._swap_choice = self._swap_choice, None
            return choice

    def _withdraw_choice(self, token: int) -> None:
        """Снять подписку на смену варианта: правило доиграло.

        Drop the variant-swap subscription: the rule has finished.
        """
        with self._lock:
            if token == self._play_token:
                self._swap_choice = None

    def _chooser_stopped(self, rule: "Rule | None" = None) -> None:
        """Сказать окну выбора, что анимацию остановили.

        Tell the chooser that the animation was stopped.

        Отдельно от ``_notify_rule_done``: там правило доиграло само, а здесь его
        прервали, и меню по нему отвечать больше не должно.
        Separate from ``_notify_rule_done``: there the rule ended by itself, while
        here it was cut short and its menu must not be answered any more.
        """
        stopped = getattr(self.chooser, "rule_stopped", None)
        if callable(stopped):
            try:
                stopped(rule)
            except TypeError:
                # заглушка без параметра / a stub without the parameter
                stopped()
            except Exception:
                log.exception("Анимации: не удалось снять меню остановленного правила")

    def _drop_choice_window(self, close: bool = False) -> None:
        """Закрыть открытый оверлей выбора, если он есть.

        Close the open chooser window, if any.

        chooser — это функция, но у настоящего оверлея есть ещё и ``cancel``:
        проверяем по наличию метода, чтобы заглушки в проверках оставались
        простыми функциями.
        chooser is a function, but the real overlay also has ``cancel``: it is
        looked up by the method's presence, so plain function stubs stay valid.
        """
        cancel = getattr(self.chooser, "cancel", None)
        if callable(cancel):
            try:
                cancel(close=close)
            except TypeError:
                # заглушка без параметра / a stub without the parameter
                cancel()
            except Exception:
                log.exception("Анимации: не удалось закрыть окно выбора")

    def _send(self, command: str, rule: Rule, quiet: bool = False, force: bool = False) -> bool:
        """Отправить команду и запомнить причину отказа.

        Send the command and remember the reason of a failure. ``quiet`` keeps a
        failed repeat in a loop from flooding the player with messages.

        Здесь же стоят ворота режима «В машине»: пока он включён, команда не
        уходит вовсе — ни `/anim`, ни `/sa`, ни нажатие клавиши (клавиша идёт
        мимо этой функции, поэтому её проверяют отдельно).
        This is also where the "In a vehicle" gate sits: while the mode is on no
        command leaves at all — neither `/anim` nor `/sa`; the key press bypasses
        this function, so it is checked on its own. ``force`` is the one exception:
        the single `/sa` that turns the mode on has to get through, or the pose
        left in the game would be the crooked one.
        """
        if not force and not self.guard_quiet():
            return False
        try:
            ok, message = self.send(command)
        except Exception as error:
            log.exception("Анимации: не удалось отправить %s", command)
            ok, message = False, str(error)[:120]
        if ok:
            log.info("Анимации: отправлено %s", command)
            return True
        self._last_error = message or "команда не отправилась"
        log.warning("Анимации: %s не отправлено — %s", command, self._last_error)
        if not quiet:
            self._emit("error", f"{command}: {self._last_error}")
        return False
