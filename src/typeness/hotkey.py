"""Global hotkey listener module for Typeness.

Listens for Shift+Command+A to toggle recording state.
Dispatches events to the main thread via a queue.Queue.
"""

import queue
import sys
import threading
import time

from pynput.keyboard import Key, KeyCode, Listener

# Event types sent to the main thread
EVENT_START_RECORDING = "start_recording"
EVENT_STOP_RECORDING = "stop_recording"
EVENT_CANCEL = "cancel"

# Hotkey combination: Shift+Command+A
# On macOS, modifier keys change the char value (e.g., Ctrl+A → '\x01'),
# breaking char-based matching. Use vk (virtual key code) instead.
_IS_MACOS = sys.platform == "darwin"
_A_KEY = KeyCode.from_vk(0) if _IS_MACOS else KeyCode.from_char("a")  # vk=0 is 'A' on macOS
_HOTKEY = {Key.shift, Key.cmd, _A_KEY}

# On macOS, subclass pynput Listener to handle CGEventTap being disabled by
# timeout — macOS kills taps whose callbacks don't respond quickly enough.
# Without this, the listener thread dies silently and hotkeys stop working.
if _IS_MACOS:
    from Quartz.CoreGraphics import CGEventTapEnable, kCGEventTapDisabledByTimeout

    class _Listener(Listener):
        def __init__(self, *args, on_tap_reset=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._tap = None
            self._on_tap_reset = on_tap_reset

        def _create_event_tap(self):
            self._tap = super()._create_event_tap()
            return self._tap

        def _handler(self, proxy, event_type, event, refcon):
            if event_type == kCGEventTapDisabledByTimeout:
                CGEventTapEnable(self._tap, True)
                if self._on_tap_reset is not None:
                    self._on_tap_reset()
                return event

            return super()._handler(proxy, event_type, event, refcon)
else:
    _Listener = Listener

_WATCHDOG_INTERVAL = 5  # seconds between listener health checks


def parse_hotkey(sc_list) -> set:
    s = set()
    for item in sc_list:
        if "vk" in item:
            s.add(KeyCode.from_vk(item["vk"]))
        elif item["name"] == "alt":
            s.add(Key.alt)
        elif item["name"] == "cmd":
            s.add(Key.cmd)
        elif item["name"] == "shift":
            s.add(Key.shift)
        elif item["name"] == "ctrl":
            s.add(Key.ctrl)
        elif item["name"] == "space":
            s.add(Key.space)
        elif "char" in item:
            s.add(KeyCode.from_char(item["char"]))
        else:
            try:
                s.add(getattr(Key, item["name"]))
            except:
                pass
    return s


class HotkeyListener:
    """Listens for global hotkeys to toggle recording or push-to-talk."""

    def __init__(self, event_queue: queue.Queue, cancel_event=None) -> None:
        self._queue = event_queue
        self._cancel_event = cancel_event
        self._recording = False
        self._busy = False
        self._pressed_keys: set = set()

        from typeness.settings import app_settings
        self._ptt_hotkey = parse_hotkey(app_settings.shortcut_push_to_talk)
        self._toggle_hotkey = parse_hotkey(app_settings.shortcut_toggle_mode)

        self._toggle_handled = False
        self._ptt_active = False

        self._suppress_current_event = False
        self._swallowed_keys: set = set()

        self._listener: _Listener | None = None
        self._should_stop = False

    def reload_config(self):
        from typeness.settings import app_settings
        self._ptt_hotkey = parse_hotkey(app_settings.shortcut_push_to_talk)
        self._toggle_hotkey = parse_hotkey(app_settings.shortcut_toggle_mode)

    @property
    def busy(self) -> bool:
        return self._busy

    @busy.setter
    def busy(self, value: bool) -> None:
        self._busy = value

    def _on_press(self, key: Key | KeyCode, injected: bool = False) -> None:
        self._suppress_current_event = False
        if injected:
            return

        normalized = self._normalize(key)
        self._pressed_keys.add(normalized)

        ptt_match = bool(self._ptt_hotkey) and self._ptt_hotkey.issubset(self._pressed_keys)
        toggle_match = bool(self._toggle_hotkey) and self._toggle_hotkey.issubset(self._pressed_keys)

        if (ptt_match and normalized in self._ptt_hotkey) or (toggle_match and normalized in self._toggle_hotkey):
            self._suppress_current_event = True
            self._swallowed_keys.add(normalized)

        if toggle_match:
            if self._toggle_handled:
                return
            self._toggle_handled = True

            if self._recording:
                # Cancel or Stop if we were recording
                self._recording = False
                self._ptt_active = False
                self._queue.put(EVENT_STOP_RECORDING)
            else:
                if self._busy:
                    if self._cancel_event is not None:
                        self._cancel_event.set()
                    self._pressed_keys.clear()
                    return
                self._recording = True
                self._queue.put(EVENT_START_RECORDING)
            self._pressed_keys.clear()

        elif ptt_match and not self._toggle_handled:
            # Only start PTT if we aren't already recording (via toggle) or busy processing
            if not self._recording and not self._busy:
                self._recording = True
                self._ptt_active = True
                self._queue.put(EVENT_START_RECORDING)

    def _on_release(self, key: Key | KeyCode, injected: bool = False) -> None:
        self._suppress_current_event = False
        if injected:
            return

        normalized = self._normalize(key)
        self._pressed_keys.discard(normalized)

        if normalized in self._swallowed_keys:
            self._suppress_current_event = True
            self._swallowed_keys.discard(normalized)

        if normalized in self._toggle_hotkey:
            self._toggle_handled = False

        # If PTT was active and we released a key that is part of the PTT hotkey
        if self._ptt_active and normalized in self._ptt_hotkey:
            self._recording = False
            self._ptt_active = False
            self._queue.put(EVENT_STOP_RECORDING)

    @staticmethod
    def _normalize(key: Key | KeyCode) -> Key | KeyCode:
        """Normalize left/right modifier variants to a single key."""
        if key in (Key.shift_l, Key.shift_r):
            return Key.shift
        if key in (Key.ctrl_l, Key.ctrl_r):
            return Key.ctrl
        if key in (Key.cmd_l, Key.cmd_r):
            return Key.cmd
        if key in (Key.alt_l, Key.alt_r, Key.alt_gr):
            return Key.alt
        if isinstance(key, KeyCode):
            if _IS_MACOS and key.vk is not None:
                return KeyCode.from_vk(key.vk)
            elif key.char is not None:
                return KeyCode.from_char(key.char.lower())
        return key

    def _on_tap_reset(self) -> None:
        """Called when CGEventTap re-enables after timeout; release events were lost."""
        self._pressed_keys.clear()
        self._toggle_handled = False
        self._ptt_active = False
        self._swallowed_keys.clear()

    def _intercept_event(self, event_type, event):
        """Called by pynput's macOS listener after _on_press/_on_release.
        If we return None, the event is swallowed by the OS.
        """
        if self._suppress_current_event:
            self._suppress_current_event = False
            return None
        return event

    def _start_listener(self) -> None:
        """Create and start a fresh pynput listener."""
        self._pressed_keys.clear()
        self._toggle_handled = False
        self._swallowed_keys.clear()

        kwargs = {
            "on_press": self._on_press,
            "on_release": self._on_release,
        }
        if _IS_MACOS:
            kwargs["on_tap_reset"] = self._on_tap_reset
            kwargs["intercept"] = self._intercept_event

        self._listener = _Listener(**kwargs)
        self._listener.daemon = True
        self._listener.start()

    def _watchdog(self) -> None:
        """Periodically check listener health and restart if dead."""
        while not self._should_stop:
            time.sleep(_WATCHDOG_INTERVAL)
            if self._should_stop:
                break
            if self._listener is not None and not self._listener.is_alive():
                print("[hotkey] Listener died, restarting...")
                self._start_listener()

    def is_running(self) -> bool:
        """Return True if the listener thread is alive."""
        return self._listener is not None and self._listener.is_alive()

    def start(self) -> None:
        """Start the global keyboard listener (runs in a daemon thread)."""
        self._should_stop = False
        self._start_listener()
        # Watchdog thread: auto-restart if the listener dies
        watchdog = threading.Thread(target=self._watchdog, daemon=True)
        watchdog.start()

    def stop(self) -> None:
        """Stop the global keyboard listener and clean up the hook."""
        self._should_stop = True
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=0.5)
            self._listener = None
