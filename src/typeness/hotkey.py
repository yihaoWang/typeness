"""Global hotkey listener module for Typeness.

Listens for Shift+Control+A to toggle recording state.
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

# Hotkey combination: Shift+Control+A
# On macOS, modifier keys change the char value (e.g., Ctrl+A → '\x01'),
# breaking char-based matching. Use vk (virtual key code) instead.
_IS_MACOS = sys.platform == "darwin"
_A_KEY = KeyCode.from_vk(0) if _IS_MACOS else KeyCode.from_char("a")  # vk=0 is 'A' on macOS
_HOTKEY = {Key.shift, Key.ctrl, _A_KEY}

# On macOS, subclass pynput Listener to handle CGEventTap being disabled by
# timeout — macOS kills taps whose callbacks don't respond quickly enough.
# Without this, the listener thread dies silently and hotkeys stop working.
if _IS_MACOS:
    from Quartz.CoreGraphics import CGEventTapEnable, kCGEventTapDisabledByTimeout

    class _Listener(Listener):
        def _create_event_tap(self):
            self._tap = super()._create_event_tap()
            return self._tap

        def _handler(self, proxy, event_type, event, refcon):
            if event_type == kCGEventTapDisabledByTimeout:
                CGEventTapEnable(self._tap, True)
                return event
            return super()._handler(proxy, event_type, event, refcon)
else:
    _Listener = Listener

_WATCHDOG_INTERVAL = 5  # seconds between listener health checks


class HotkeyListener:
    """Listens for Shift+Control+A to toggle recording on/off.

    State machine: idle -> recording -> idle
    - First hotkey press: idle -> recording (sends EVENT_START_RECORDING)
    - Second hotkey press: recording -> idle (sends EVENT_STOP_RECORDING)

    Defenses:
    - Ignores injected (synthetic) key events to avoid capturing our own Ctrl+V
    - busy flag prevents starting new recording during processing
    - Watchdog auto-restarts the listener if it dies (e.g., macOS tap timeout)
    """

    def __init__(self, event_queue: queue.Queue, cancel_event=None) -> None:
        self._queue = event_queue
        self._cancel_event = cancel_event
        self._recording = False
        self._busy = False
        self._pressed_keys: set = set()
        self._hotkey_handled = False
        self._listener: _Listener | None = None
        self._should_stop = False

    @property
    def busy(self) -> bool:
        return self._busy

    @busy.setter
    def busy(self, value: bool) -> None:
        self._busy = value

    def _on_press(self, key: Key | KeyCode, injected: bool = False) -> None:
        # Ignore synthetic (injected) key events
        if injected:
            return

        # Normalize: treat Key.shift_l / Key.shift_r as Key.shift, etc.
        normalized = self._normalize(key)
        self._pressed_keys.add(normalized)

        # Check if hotkey combination is active
        if not _HOTKEY.issubset(self._pressed_keys):
            return

        # Prevent repeated firing while keys are held down
        if self._hotkey_handled:
            return
        self._hotkey_handled = True

        if self._recording:
            self._recording = False
            self._queue.put(EVENT_STOP_RECORDING)
        else:
            if self._busy:
                # Cancel ongoing processing
                if self._cancel_event is not None:
                    self._cancel_event.set()
                return
            self._recording = True
            self._queue.put(EVENT_START_RECORDING)

    def _on_release(self, key: Key | KeyCode, injected: bool = False) -> None:
        if injected:
            return

        normalized = self._normalize(key)
        self._pressed_keys.discard(normalized)

        # Reset handled flag when any hotkey member is released
        if normalized in _HOTKEY:
            self._hotkey_handled = False

    @staticmethod
    def _normalize(key: Key | KeyCode) -> Key | KeyCode:
        """Normalize left/right modifier variants to a single key."""
        if key in (Key.shift_l, Key.shift_r):
            return Key.shift
        if key in (Key.ctrl_l, Key.ctrl_r):
            return Key.ctrl
        if isinstance(key, KeyCode):
            if _IS_MACOS and key.vk is not None:
                # On macOS, normalize to vk-only KeyCode so hash is consistent
                # regardless of which modifiers change the char value.
                return KeyCode.from_vk(key.vk)
            elif key.char is not None:
                return KeyCode.from_char(key.char.lower())
        return key

    def _start_listener(self) -> None:
        """Create and start a fresh pynput listener."""
        self._pressed_keys.clear()
        self._hotkey_handled = False
        self._listener = _Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
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
