"""Mac menu bar icon for Typeness.

Displays recording state in the menu bar and provides click-to-record and quit controls.
Uses SF Symbols as template images to match the native macOS menu bar icon style.
"""

import threading

import rumps
from AppKit import NSApplication, NSImage

from typeness.hotkey import EVENT_START_RECORDING, EVENT_STOP_RECORDING

# SF Symbol name for each state
_SF_SYMBOLS = {
    "recording": "mic.fill",
    "transcribing": "waveform",
    "processing": "waveform",
}

# Spinner frames for transcribing/processing (cycling SF symbols)
_SPINNER_SYMBOLS = [
    "waveform",
    "waveform.badge.microphone",
    "waveform",
    "mic",
]

_STATUS_LABELS = {
    "idle": "狀態：待機",
    "recording": "狀態：錄音中",
    "transcribing": "狀態：辨識中 (1/2)",
    "processing": "狀態：後處理中 (2/2)",
}

_TOGGLE_LABELS = {
    "idle": "開始錄音",
    "recording": "停止錄音",
    "transcribing": "取消",
    "processing": "取消",
}


class TypenessMenuBar(rumps.App):
    """Menu bar icon that reflects Typeness state and provides basic controls."""

    def __init__(self, event_queue, cleanup_fn, cancel_event=None):
        super().__init__("Typeness", title="", quit_button=None)

        self._event_queue = event_queue
        self._cleanup_fn = cleanup_fn
        self._cancel_event = cancel_event
        self._lock = threading.Lock()
        self._state = "idle"
        self._frame = 0

        self._status_item = rumps.MenuItem(_STATUS_LABELS["idle"])
        self._status_item.set_callback(None)  # not clickable

        self._toggle_item = rumps.MenuItem("開始錄音", callback=self._on_toggle)

        self.menu = [
            self._status_item,
            None,
            self._toggle_item,
            None,
            rumps.MenuItem("退出", callback=self._on_quit),
        ]

        # Hide from Dock and main menu bar — run as a pure status-bar-only app
        rumps.events.before_start.register(self._hide_from_dock)

        # Poll state every 0.2s on the main thread to update the icon/menu
        self._timer = rumps.Timer(self._poll_state, 0.2)
        self._timer.start()

    # --- App lifecycle ---

    def _hide_from_dock(self):
        """Called via before_start: make this a background-only app with no Dock icon or main menu bar."""
        NSApplication.sharedApplication().setActivationPolicy_(2)  # NSApplicationActivationPolicyProhibited
        self._nsapp.nsstatusitem.setVisible_(False)  # hide until first recording starts

    def _set_sf_symbol(self, symbol_name: str) -> None:
        """Set the menu bar button to display an SF Symbol as a template image."""
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
        if image is not None:
            image.setTemplate_(True)  # adapts to light/dark mode like native icons
            button = self._nsapp.nsstatusitem.button()
            button.setImage_(image)
            button.setTitle_("")

    # --- Called from worker thread ---

    def set_state(self, state: str) -> None:
        """Thread-safe state update. Worker thread writes; main thread reads via timer."""
        with self._lock:
            self._state = state

    # --- Main-thread callbacks ---

    def _poll_state(self, _) -> None:
        with self._lock:
            state = self._state

        # Show the menu bar icon only when active (recording / transcribing / processing)
        visible = state != "idle"
        self._nsapp.nsstatusitem.setVisible_(visible)

        if state in ("transcribing", "processing"):
            self._frame = (self._frame + 1) % len(_SPINNER_SYMBOLS)
            self._set_sf_symbol(_SPINNER_SYMBOLS[self._frame])
        elif state in _SF_SYMBOLS:
            self._frame = 0
            self._set_sf_symbol(_SF_SYMBOLS[state])

        self._status_item.title = _STATUS_LABELS.get(state, _STATUS_LABELS["idle"])

        toggle_label = _TOGGLE_LABELS.get(state)
        if state in ("transcribing", "processing"):
            self._toggle_item.title = toggle_label  # "取消"
            self._toggle_item.set_callback(self._on_cancel)
        else:
            self._toggle_item.title = toggle_label or "開始錄音"
            self._toggle_item.set_callback(self._on_toggle)

    def _on_toggle(self, _) -> None:
        with self._lock:
            state = self._state
        if state == "idle":
            self._event_queue.put(EVENT_START_RECORDING)
        elif state == "recording":
            self._event_queue.put(EVENT_STOP_RECORDING)

    def _on_cancel(self, _) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _on_quit(self, _) -> None:
        self._cleanup_fn()
        rumps.quit_application()
