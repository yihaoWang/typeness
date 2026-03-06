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
    NSView,
    NSWindow,
)
from Foundation import NSMakeRect, NSMakeSize, NSObject

from typeness.hotkey import EVENT_START_RECORDING, EVENT_STOP_RECORDING
from typeness.settings import Settings

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


# ---------------------------------------------------------------------------
# Settings window
# ---------------------------------------------------------------------------

class _SettingsDelegate(NSObject):
    """NSWindow delegate and checkbox target for the settings panel."""

    # Set by _SettingsWindow.show() before the window appears
    _settings: object = None
    _on_change: object = None

    def windowShouldClose_(self, sender):
        sender.orderOut_(None)
        return False

    def checkboxChanged_(self, sender):
        value = sender.state() == 1
        if self._settings is not None:
            self._settings.show_menubar_icon_always = value
        if self._on_change is not None:
            self._on_change(value)


class _SettingsWindow:
    """Native AppKit settings panel for Typeness."""

    _WIDTH = 380
    _HEIGHT = 230

    def __init__(self, app_settings: Settings) -> None:
        self._settings = app_settings
        self._window: NSWindow | None = None
        self._delegate = _SettingsDelegate.alloc().init()

    # ---- Build ----

    def _build(self) -> None:
        screen_frame = NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - self._WIDTH) / 2
        y = (screen_frame.size.height - self._HEIGHT) / 2

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (self._WIDTH, self._HEIGHT)),
            NSTitledWindowMask | NSClosableWindowMask,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("Typeness 設定")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self._delegate)
        win.setMinSize_(NSMakeSize(self._WIDTH, self._HEIGHT))
        win.setMaxSize_(NSMakeSize(self._WIDTH, self._HEIGHT))

        content = win.contentView()

        # ---- Section: 選單列 ----
        section_label = self._make_section_header("選單列", y=168)
        content.addSubview_(section_label)

        separator = NSBox.alloc().initWithFrame_(NSMakeRect(20, 158, self._WIDTH - 40, 1))
        separator.setBoxType_(2)  # NSBoxSeparator
        content.addSubview_(separator)

        # Checkbox
        checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(20, 120, self._WIDTH - 40, 24))
        checkbox.setButtonType_(6)  # NSSwitchButton
        checkbox.setTitle_("始終在選單列顯示圖示")
        checkbox.setState_(1 if self._settings.show_menubar_icon_always else 0)
        checkbox.setTarget_(self._delegate)
        checkbox.setFont_(NSFont.systemFontOfSize_(13.0))
        # Store ref for callback wiring after building
        self._checkbox = checkbox
        content.addSubview_(checkbox)

        # Description
        desc = self._make_description(
            "啟用後，待機時顯示填滿麥克風圖示（較顯眼）。\n停用時顯示輪廓圖示（較低調）。",
            y=65,
        )
        content.addSubview_(desc)

        # ---- Section: 快捷鍵 ----
        hotkey_section = self._make_section_header("快捷鍵", y=46)
        content.addSubview_(hotkey_section)

        hotkey_sep = NSBox.alloc().initWithFrame_(NSMakeRect(20, 36, self._WIDTH - 40, 1))
        hotkey_sep.setBoxType_(2)
        content.addSubview_(hotkey_sep)

        hotkey_label = self._make_description("開始 / 停止錄音：⇧ Control A", y=10)
        content.addSubview_(hotkey_label)

        self._window = win

    def _make_section_header(self, text: str, y: float) -> NSTextField:
        tf = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y, self._WIDTH - 40, 20))
        tf.setStringValue_(text)
        tf.setEditable_(False)
        tf.setBordered_(False)
        tf.setBackgroundColor_(NSColor.clearColor())
        tf.setFont_(NSFont.boldSystemFontOfSize_(11.0))
        tf.setTextColor_(NSColor.secondaryLabelColor())
        return tf

    def _make_description(self, text: str, y: float) -> NSTextField:
        tf = NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, self._WIDTH - 60, 48))
        tf.setStringValue_(text)
        tf.setEditable_(False)
        tf.setBordered_(False)
        tf.setBackgroundColor_(NSColor.clearColor())
        tf.setFont_(NSFont.systemFontOfSize_(11.0))
        tf.setTextColor_(NSColor.secondaryLabelColor())
        return tf

    # ---- Public API ----

    def show(self, on_change_callback) -> None:
        """Show (or bring to front) the settings window."""
        if self._window is None:
            self._build()
            # Wire checkbox action after build
            self._checkbox.setAction_("checkboxChanged:")
            # Attach the handler via a closure stored on delegate
            self._delegate._on_change = on_change_callback
            self._delegate._checkbox = self._checkbox
            self._delegate._settings = self._settings

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.orderFrontRegardless()

    def is_show_always(self) -> bool:
        return self._settings.show_menubar_icon_always



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
        self._accessibility_error: bool = not accessibility_granted

        self._app_settings = Settings()
        self._settings_win = _SettingsWindow(self._app_settings)

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
        rumps.events.before_start.register(self._setup_recording_overlay)

        # Poll state every 0.2s on the main thread to update the icon/menu
        self._timer = rumps.Timer(self._poll_state, 0.2)
        self._timer.start()

    # --- App lifecycle ---

    def _hide_from_dock(self):
        """Called via before_start: LSUIElement=true in Info.plist already hides Dock icon."""
        self._nsapp.nsstatusitem.setVisible_(True)
        self._set_sf_symbol("mic")

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

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (size, size)),
            NSBorderlessWindowMask,
            NSBackingStoreBuffered,
            False,
        )
        win.setBackgroundColor_(NSColor.clearColor())
        win.setOpaque_(False)
        win.setAlphaValue_(0.80)
        win.setLevel_(999)
        win.setIgnoresMouseEvents_(True)
        win.setCollectionBehavior_(1 << 1)  # NSWindowCollectionBehaviorMoveToActiveSpace
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

    def _setup_recording_overlay(self) -> None:
        """Build the red-dot recording indicator overlay window once at startup (hidden)."""
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
        win.setAlphaValue_(0.0)
        win.setLevel_(999)
        win.setIgnoresMouseEvents_(True)
        win.setCollectionBehavior_(1 << 1)  # NSWindowCollectionBehaviorMoveToActiveSpace
        win.setReleasedWhenClosed_(False)

        bg = NSView.alloc().initWithFrame_(((0, 0), (size, size)))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
        bg.layer().setCornerRadius_(size / 2)

        icon_size = 16.0
        icon_origin = ((size - icon_size) / 2, (size - icon_size) / 2)
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("mic.fill", None)
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

        if state in ("transcribing", "processing"):
            self._frame = (self._frame + 1) % len(_SPINNER_SYMBOLS)
            self._set_sf_symbol(_SPINNER_SYMBOLS[self._frame])
        elif state in _SF_SYMBOLS:
            self._frame = 0
            self._set_sf_symbol(_SF_SYMBOLS[state])
        elif state == "idle":
            self._frame = 0
            # Prominent mic.fill when "show always" is on; subtle mic when off
            self._set_sf_symbol("mic.fill" if show_always else "mic")

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

    def _on_settings(self, _) -> None:
        self._settings_win.show(on_change_callback=self._on_setting_changed)

    def _on_setting_changed(self, _value: bool) -> None:
        # The poll timer will pick up the new value on the next tick
        pass

    def _on_quit(self, _) -> None:
        self._cleanup_fn()
        rumps.quit_application()
