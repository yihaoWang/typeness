"""Mac menu bar icon for Typeness.

Displays recording state in the menu bar and provides click-to-record and quit controls.
Uses SF Symbols as template images to match the native macOS menu bar icon style.
"""

import threading
import time

import rumps
from AppKit import (
    NSApplication, NSBackingStoreBuffered, NSBorderlessWindowMask,
    NSColor, NSImage, NSImageView, NSScreen, NSView, NSWindow,
)

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
        self._done_until: float = 0
        self._overlay: NSWindow | None = None

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

        # Build overlay once; show/hide via orderFrontRegardless/orderOut to avoid
        # repeatedly creating windows which disrupts the CGEventTap.
        rumps.events.before_start.register(self._setup_overlay)

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
            image.setTemplate_(True)
            button = self._nsapp.nsstatusitem.button()
            button.setImage_(image)
            button.setTitle_("")

    def _setup_overlay(self) -> None:
        """Build the green-dot overlay window once at startup (hidden). Show/hide via order methods."""
        size = 30.0
        screen_frame = NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - size) / 2
        y = 80.0

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (size, size)),
            NSBorderlessWindowMask,
            NSBackingStoreBuffered,
            False,
        )
        win.setBackgroundColor_(NSColor.clearColor())
        win.setOpaque_(False)
        win.setAlphaValue_(0.55)
        win.setLevel_(999)
        win.setIgnoresMouseEvents_(True)
        win.setCollectionBehavior_(1 << 2)
        win.setReleasedWhenClosed_(False)

        bg = NSView.alloc().initWithFrame_(((0, 0), (size, size)))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(NSColor.systemGreenColor().CGColor())
        bg.layer().setCornerRadius_(size / 2)

        icon_size = 16.0
        icon_origin = ((size - icon_size) / 2, (size - icon_size) / 2)
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("checkmark", None)
        image_view = NSImageView.alloc().initWithFrame_((icon_origin, (icon_size, icon_size)))
        image_view.setImage_(image)
        image_view.setContentTintColor_(NSColor.whiteColor())
        bg.addSubview_(image_view)

        win.setContentView_(bg)
        self._overlay = win  # hidden until first "done" state

    # --- Called from worker thread ---

    def set_state(self, state: str) -> None:
        """Thread-safe state update. Worker thread writes; main thread reads via timer."""
        with self._lock:
            self._state = state
            if state == "done":
                self._done_until = time.monotonic() + 1.5

    # --- Main-thread callbacks ---

    def _poll_state(self, _) -> None:
        with self._lock:
            state = self._state

        # Auto-revert "done" state after the flash duration
        if state == "done":
            with self._lock:
                if time.monotonic() >= self._done_until:
                    self._state = "idle"
                    state = "idle"

        # Show the menu bar icon only when active (recording / transcribing / processing / done)
        visible = state != "idle"
        self._nsapp.nsstatusitem.setVisible_(visible)

        if state in ("transcribing", "processing"):
            self._frame = (self._frame + 1) % len(_SPINNER_SYMBOLS)
            self._set_sf_symbol(_SPINNER_SYMBOLS[self._frame])
        elif state in _SF_SYMBOLS:
            self._frame = 0
            self._set_sf_symbol(_SF_SYMBOLS[state])

        # Show/hide the bottom-center green dot overlay for "done"
        if self._overlay is not None:
            if state == "done":
                self._overlay.orderFrontRegardless()
            else:
                self._overlay.orderOut_(None)

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
        if state in ("idle", "done"):
            self._event_queue.put(EVENT_START_RECORDING)
        elif state == "recording":
            self._event_queue.put(EVENT_STOP_RECORDING)

    def _on_cancel(self, _) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _on_quit(self, _) -> None:
        self._cleanup_fn()
        rumps.quit_application()
