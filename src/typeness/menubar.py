"""Mac menu bar icon for Typeness.

Displays recording state in the menu bar and provides click-to-record and quit controls.
Uses SF Symbols as template images to match the native macOS menu bar icon style.
"""

import threading
import time

import rumps
from AppKit import (
    NSAnimationContext,
    NSApplication,
    NSBackingStoreBuffered,
    NSBorderlessWindowMask,
    NSBox,
    NSButton,
    NSClosableWindowMask,
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSScreen,
    NSTextField,
    NSTitledWindowMask,
    NSPanel,
    NSView,
    NSWindow,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakeRect, NSMakeSize, NSObject

from typeness.hotkey import EVENT_START_RECORDING, EVENT_STOP_RECORDING
from typeness.settings import Settings

# SF Symbol name for each state
_SF_SYMBOLS = {
    "loading": "hourglass",
    "recording": "person.wave.2.fill",
    "transcribing": "waveform",
    "processing": "waveform",
}

_STATUS_LABELS = {
    "loading": "狀態：初始化中...",
    "idle": "狀態：待機",
    "recording": "狀態：錄音中",
    "transcribing": "狀態：辨識中 (1/2)",
    "processing": "狀態：後處理中 (2/2)",
}

_TOGGLE_LABELS = {
    "loading": "請稍候",
    "idle": "開始錄音",
    "recording": "停止錄音",
    "transcribing": "取消",
    "processing": "取消",
}


# ---------------------------------------------------------------------------
# Settings window (Handled by settings_ui.py)
# ---------------------------------------------------------------------------
from typeness.settings_ui import SettingsUI

# ---------------------------------------------------------------------------
# Menu bar app
# ---------------------------------------------------------------------------

class TypenessMenuBar(rumps.App):
    """Menu bar icon that reflects Typeness state and provides basic controls."""

    def __init__(self, event_queue, cleanup_fn, cancel_event=None, *, accessibility_granted=True):
        super().__init__("Typeness", title="", quit_button=None)

        self._event_queue = event_queue
        self._cleanup_fn = cleanup_fn
        self._cancel_event = cancel_event
        self._lock = threading.Lock()
        self._state = "idle"
        self._frame = 0
        self._done_until: float = 0
        self._overlay: NSWindow | None = None
        self._recording_overlay: NSWindow | None = None
        self._processing_overlay: NSWindow | None = None
        self._accessibility_error: bool = not accessibility_granted

        self._app_settings = Settings()
        self._settings_win = SettingsUI(self._on_setting_changed)
        self._external_settings_callback = None

        self._status_item = rumps.MenuItem(_STATUS_LABELS["idle"])
        self._status_item.set_callback(None)  # not clickable

        self._toggle_item = rumps.MenuItem("開始錄音", callback=self._on_toggle)

        self._accessibility_item = rumps.MenuItem("⚠️ 需要輔助使用權限", callback=None)
        self._open_prefs_item = rumps.MenuItem("開啟系統設定...", callback=self._on_open_accessibility)

        self.menu = [
            self._status_item,
            None,
            self._toggle_item,
            None,
            rumps.MenuItem("設定...", callback=self._on_settings),
            None,
            rumps.MenuItem("退出", callback=self._on_quit),
        ]

        # Hide from Dock and main menu bar — run as a pure status-bar-only app
        rumps.events.before_start.register(self._hide_from_dock)

        # Build overlays once; show/hide via orderFrontRegardless/orderOut to avoid
        # repeatedly creating windows which disrupts the CGEventTap.
        rumps.events.before_start.register(self._setup_overlay)
        rumps.events.before_start.register(self._setup_processing_overlay)
        rumps.events.before_start.register(self._setup_recording_overlay)

        # Poll state every 0.2s on the main thread to update the icon/menu
        self._timer = rumps.Timer(self._poll_state, 0.2)
        self._timer.start()

    # --- App lifecycle ---

    def _hide_from_dock(self):
        """Called via before_start: LSUIElement=true in Info.plist already hides Dock icon."""
        self._nsapp.nsstatusitem.setVisible_(True)
        self._set_sf_symbol("person.wave.2")

    def _set_sf_symbol(self, symbol_name: str) -> None:
        """Set the menu bar button to display an SF Symbol as a template image."""
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
        button = self._nsapp.nsstatusitem.button()
        if image is not None:
            image.setTemplate_(True)
            button.setImage_(image)
            button.setTitle_("")
        else:
            button.setImage_(None)
            button.setTitle_("⏺")  # visible fallback if SF Symbols unavailable

    def _setup_overlay(self) -> None:
        """Build the green-dot overlay window once at startup (hidden). Show/hide via order methods."""
        size = 30.0
        screen_frame = NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - size) / 2
        y = 80.0

        win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (size, size)),
            NSBorderlessWindowMask | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        win.setBackgroundColor_(NSColor.clearColor())
        win.setOpaque_(False)
        win.setAlphaValue_(0.80)
        win.setLevel_(999)
        win.setIgnoresMouseEvents_(True)
        win.setFloatingPanel_(True)
        win.setHidesOnDeactivate_(False)
        win.setCollectionBehavior_(
            (1 << 0) | (1 << 8) | (1 << 6)  # CanJoinAllSpaces | FullScreenAuxiliary | IgnoresCycle
        )
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

    def _setup_processing_overlay(self) -> None:
        """Build the orange-dot processing indicator overlay window once at startup (hidden)."""
        size = 30.0
        screen_frame = NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - size) / 2
        y = 80.0

        win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (size, size)),
            NSBorderlessWindowMask | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        win.setBackgroundColor_(NSColor.clearColor())
        win.setOpaque_(False)
        win.setAlphaValue_(0.0)
        win.setLevel_(999)
        win.setIgnoresMouseEvents_(True)
        win.setFloatingPanel_(True)
        win.setHidesOnDeactivate_(False)
        win.setCollectionBehavior_(
            (1 << 0) | (1 << 8) | (1 << 6)  # CanJoinAllSpaces | FullScreenAuxiliary | IgnoresCycle
        )
        win.setReleasedWhenClosed_(False)

        bg = NSView.alloc().initWithFrame_(((0, 0), (size, size)))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(NSColor.systemOrangeColor().CGColor())
        bg.layer().setCornerRadius_(size / 2)

        icon_size = 16.0
        icon_origin = ((size - icon_size) / 2, (size - icon_size) / 2)
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("waveform", None)
        image_view = NSImageView.alloc().initWithFrame_((icon_origin, (icon_size, icon_size)))
        image_view.setImage_(image)
        image_view.setContentTintColor_(NSColor.whiteColor())
        bg.addSubview_(image_view)

        win.setContentView_(bg)
        self._processing_overlay = win

    def _setup_recording_overlay(self) -> None:
        """Build the red-dot recording indicator overlay window once at startup (hidden)."""
        size = 30.0
        screen_frame = NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - size) / 2
        y = 80.0

        win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (size, size)),
            NSBorderlessWindowMask | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        win.setBackgroundColor_(NSColor.clearColor())
        win.setOpaque_(False)
        win.setAlphaValue_(0.0)
        win.setLevel_(999)
        win.setIgnoresMouseEvents_(True)
        win.setFloatingPanel_(True)
        win.setHidesOnDeactivate_(False)
        win.setCollectionBehavior_(
            (1 << 0) | (1 << 8) | (1 << 6)  # CanJoinAllSpaces | FullScreenAuxiliary | IgnoresCycle
        )
        win.setReleasedWhenClosed_(False)

        bg = NSView.alloc().initWithFrame_(((0, 0), (size, size)))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
        bg.layer().setCornerRadius_(size / 2)

        icon_size = 16.0
        icon_origin = ((size - icon_size) / 2, (size - icon_size) / 2)
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("person.wave.2.fill", None)
        image_view = NSImageView.alloc().initWithFrame_((icon_origin, (icon_size, icon_size)))
        image_view.setImage_(image)
        image_view.setContentTintColor_(NSColor.whiteColor())
        bg.addSubview_(image_view)

        win.setContentView_(bg)
        self._recording_overlay = win  # hidden until recording state

    # --- Called from worker thread ---

    def set_accessibility_error(self) -> None:
        """Called from background thread when Accessibility permission is missing."""
        with self._lock:
            self._accessibility_error = True

    def clear_accessibility_error(self) -> None:
        """Called from background thread when Accessibility permission is granted."""
        with self._lock:
            self._accessibility_error = False

    def set_state(self, state: str) -> None:
        """Thread-safe state update. Worker thread writes; main thread reads via timer."""
        with self._lock:
            self._state = state
            if state == "done":
                self._done_until = time.monotonic() + 1.0

    # --- Main-thread callbacks ---

    def _poll_state(self, _) -> None:
        with self._lock:
            accessibility_error = self._accessibility_error
            state = self._state

        # Always ensure the status item is visible
        self._nsapp.nsstatusitem.setVisible_(True)

        if accessibility_error:
            self._status_item.title = "⚠️ 需要輔助使用權限"
            self._toggle_item.title = "開啟系統設定..."
            self._toggle_item.set_callback(self._on_open_accessibility)
            self._set_sf_symbol("exclamationmark.triangle")
            return

        # Auto-revert "done" state after the flash duration
        if state == "done":
            with self._lock:
                if time.monotonic() >= self._done_until:
                    self._state = "idle"
                    state = "idle"

        # Icon is always visible so the user can always access Settings.
        # The "show_menubar_icon_always" setting controls whether to show it
        # in a more prominent way when idle (solid mic) vs. a dimmed mic.
        show_always = self._app_settings.show_menubar_icon_always

        if state in _SF_SYMBOLS:
            self._frame = 0
            self._set_sf_symbol(_SF_SYMBOLS[state])
        elif state == "idle":
            self._frame = 0
            # Prominent fill when "show always" is on; subtle outline when off
            self._set_sf_symbol("person.wave.2.fill" if show_always else "person.wave.2")

        # Show/hide the bottom-center red dot overlay for "recording"
        if self._recording_overlay is not None:
            if state == "recording":
                self._recording_overlay.setAlphaValue_(0.85)
                self._recording_overlay.orderFrontRegardless()
            else:
                NSAnimationContext.beginGrouping()
                NSAnimationContext.currentContext().setDuration_(0.3)
                self._recording_overlay.animator().setAlphaValue_(0.0)
                NSAnimationContext.endGrouping()

        # Show/hide the bottom-center orange dot overlay for "transcribing"/"processing"
        if self._processing_overlay is not None:
            if state in ("transcribing", "processing"):
                self._processing_overlay.setAlphaValue_(0.85)
                self._processing_overlay.orderFrontRegardless()
            else:
                NSAnimationContext.beginGrouping()
                NSAnimationContext.currentContext().setDuration_(0.3)
                self._processing_overlay.animator().setAlphaValue_(0.0)
                NSAnimationContext.endGrouping()

        # Show/hide the bottom-center green dot overlay for "done"
        if self._overlay is not None:
            if state == "done":
                self._overlay.setAlphaValue_(0.85)
                self._overlay.orderFrontRegardless()
            else:
                NSAnimationContext.beginGrouping()
                NSAnimationContext.currentContext().setDuration_(0.8)
                self._overlay.animator().setAlphaValue_(0.0)
                NSAnimationContext.endGrouping()

        self._status_item.title = _STATUS_LABELS.get(state, _STATUS_LABELS["idle"])

        toggle_label = _TOGGLE_LABELS.get(state)
        if state in ("transcribing", "processing"):
            self._toggle_item.title = toggle_label  # "取消"
            self._toggle_item.set_callback(self._on_cancel)
        elif state == "loading":
            self._toggle_item.title = toggle_label
            self._toggle_item.set_callback(None)
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

    def _on_open_accessibility(self, _) -> None:
        import subprocess
        subprocess.run([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])

    def set_settings_callback(self, cb) -> None:
        self._external_settings_callback = cb

    def _on_settings(self, _) -> None:
        self._settings_win.show()

    def _on_setting_changed(self) -> None:
        if self._external_settings_callback:
            self._external_settings_callback()

    def _on_quit(self, _) -> None:
        self._cleanup_fn()
        rumps.quit_application()
