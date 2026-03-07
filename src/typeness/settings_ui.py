import os
import Foundation
import AppKit
import objc
from typeness.settings import app_settings

# --- Shortcut Utilities ---

def _key_code_to_name(keycode, chars):
    """Map macOS keycode to pynput key name style."""
    if chars and chars.strip():
        return {"char": chars.lower()}

    # Map common special keys
    special_keys = {
        36: "enter",
        48: "tab",
        49: "space",
        51: "backspace",
        53: "esc",
        123: "left",
        124: "right",
        125: "down",
        126: "up",
    }
    if keycode in special_keys:
        return {"name": special_keys[keycode]}
    return {"vk": keycode}

def _shortcut_to_string(sc_list) -> str:
    """Convert settings shortcut list to display string."""
    parts = []

    mod_symbols = {
        "cmd": "⌘",
        "shift": "⇧",
        "alt": "⌥",
        "ctrl": "⌃"
    }

    for item in sc_list:
        if "name" in item:
            name = item["name"]
            if name in mod_symbols:
                parts.append(mod_symbols[name])
            elif name == "space":
                parts.append("␣")
            else:
                parts.append(name.upper())
        elif "char" in item:
            parts.append(item["char"].upper())
        elif "vk" in item:
            # Simplistic fallback
            parts.append(f"[{item['vk']}]")

    return " ".join(parts)


class ShortcutButton(AppKit.NSButton):
    def initWithFrame_(self, frame):
        self = objc.super(ShortcutButton, self).initWithFrame_(frame)
        if self:
            self.recording = False
            self.setting_key = None
            self.on_change = None
        return self

    def mouseDown_(self, event):
        if not self.recording:
            self.recording = True
            self.setTitle_("Recording...")
            self.window().makeFirstResponder_(self)
        else:
            self.recording = False
            self._update_title()

    def keyDown_(self, event):
        if not self.recording:
            objc.super(ShortcutButton, self).keyDown_(event)
            return

        mods = event.modifierFlags()

        # Don't trigger on just modifier keys without a real key
        # (Though technically PTT can be just modifiers, we'll allow single keys if chars exists)
        chars = event.charactersIgnoringModifiers()
        keycode = event.keyCode()

        # Ignore if it's purely a modifier key press
        if keycode in [54, 55, 56, 59, 60, 61, 62, 63]: # Command, Shift, Option, Control
            return

        shortcut = []
        if mods & AppKit.NSEventModifierFlagShift:
            shortcut.append({"name": "shift"})
        if mods & AppKit.NSEventModifierFlagControl:
            shortcut.append({"name": "ctrl"})
        if mods & AppKit.NSEventModifierFlagOption:
            shortcut.append({"name": "alt"})
        if mods & AppKit.NSEventModifierFlagCommand:
            shortcut.append({"name": "cmd"})

        shortcut.append(_key_code_to_name(keycode, chars))

        setattr(app_settings, self.setting_key, shortcut)
        app_settings.save()

        self.recording = False
        self._update_title()
        self.window().makeFirstResponder_(None)

        if self.on_change:
            self.on_change()

    def _update_title(self):
        val = getattr(app_settings, self.setting_key)
        self.setTitle_(_shortcut_to_string(val))


class SettingsWindowController(Foundation.NSObject):
    def windowShouldClose_(self, sender):
        sender.orderOut_(None)
        return False

    def showFloatingChanged_(self, sender):
        app_settings.show_floating_window = (sender.state() == AppKit.NSControlStateValueOn)

    def floatingPosChanged_(self, sender):
        pass # Deprecated, position is now fixed to center

    def confirmInsertChanged_(self, sender):
        app_settings.confirm_before_inserting = (sender.state() == AppKit.NSControlStateValueOn)

    def openMicSettings_(self, sender):
        import subprocess
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"])

    def openAccSettings_(self, sender):
        import subprocess
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])


class SettingsUI:
    def __init__(self, on_change_callback):
        self.on_change = on_change_callback
        self.window = None
        self.controller = SettingsWindowController.alloc().init()

    def _create_label(self, frame, text, size=13, weight=AppKit.NSFontWeightRegular, color=AppKit.NSColor.labelColor()):
        lbl = AppKit.NSTextField.labelWithString_(text)
        lbl.setFrame_(frame)
        lbl.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, weight))
        lbl.setTextColor_(color)
        return lbl

    def _create_box(self, frame):
        box = AppKit.NSBox.alloc().initWithFrame_(frame)
        box.setBoxType_(AppKit.NSBoxCustom)
        box.setBorderType_(AppKit.NSLineBorder)
        box.setBorderColor_(AppKit.NSColor.quaternaryLabelColor())
        box.setBorderWidth_(1.0)
        box.setCornerRadius_(8.0)
        box.setContentViewMargins_(Foundation.NSMakeSize(0, 0))
        box.setFillColor_(AppKit.NSColor.selectedTextBackgroundColor().colorWithAlphaComponent_(0.1))
        return box

    def _create_separator(self, frame):
        sep = AppKit.NSBox.alloc().initWithFrame_(frame)
        sep.setBoxType_(AppKit.NSBoxCustom)
        sep.setBorderType_(AppKit.NSNoBorder)
        sep.setFillColor_(AppKit.NSColor.quaternaryLabelColor())
        return sep

    def _create_section_header(self, content, x, y, box_w, sf_symbol, title, color=None):
        """Create a section header with SF Symbol icon + label."""
        if color is None:
            color = AppKit.NSColor.systemTealColor()
        img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(sf_symbol, None)
        iv = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(x, y, 18, 18))
        iv.setImage_(img)
        iv.setContentTintColor_(color)
        content.addSubview_(iv)
        lbl = self._create_label(Foundation.NSMakeRect(x + 24, y, 200, 18), title, 13, AppKit.NSFontWeightSemibold)
        content.addSubview_(lbl)

    def _check_mic_permission(self):
        """Check microphone permission status via AVCaptureDevice."""
        try:
            AVCaptureDevice = objc.lookUpClass("AVCaptureDevice")
            # authorizationStatusForMediaType: 0=NotDetermined, 1=Restricted, 2=Denied, 3=Authorized
            status = AVCaptureDevice.authorizationStatusForMediaType_("soun")  # AVMediaTypeAudio = "soun"
            return status == 3
        except Exception:
            return False

    def _check_accessibility_permission(self):
        """Check accessibility permission status."""
        from ApplicationServices import AXIsProcessTrusted
        return AXIsProcessTrusted()

    def _add_two_row_box(self, content, cy, margin, box_w, rows):
        """Create a rounded box with two rows of content.

        Each row is a dict with keys: title, subtitle, and one of:
          widget='switch', value=bool, target=obj, action=str
          widget='shortcut', setting_key=str, on_change=callable
          widget='status', granted=bool, target=obj, action=str
        Returns the new cy after the box.
        """
        box_h = 100
        row_h = 42
        pad_top = 8
        pad_x = 16

        box = self._create_box(Foundation.NSMakeRect(margin, cy - box_h, box_w, box_h))

        for i, row in enumerate(rows):
            ry = box_h - pad_top - row_h * i - row_h // 2

            # Title + subtitle
            lbl = self._create_label(
                Foundation.NSMakeRect(pad_x, ry + 4, box_w - 160, 18),
                row["title"], 13, AppKit.NSFontWeightMedium)
            sub = self._create_label(
                Foundation.NSMakeRect(pad_x, ry - 12, box_w - 160, 15),
                row["subtitle"], 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
            box.addSubview_(lbl)
            box.addSubview_(sub)

            # Right-side widget
            w = row.get("widget")
            if w == "switch":
                sw = AppKit.NSSwitch.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 60, ry - 2, 40, 24))
                sw.setState_(AppKit.NSControlStateValueOn if row["value"] else AppKit.NSControlStateValueOff)
                sw.setTarget_(row["target"])
                sw.setAction_(row["action"])
                box.addSubview_(sw)
            elif w == "shortcut":
                btn = ShortcutButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 90, ry - 2, 72, 24))
                btn.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
                btn.setting_key = row["setting_key"]
                btn.on_change = row["on_change"]
                btn._update_title()
                box.addSubview_(btn)
            elif w == "status":
                if row["granted"]:
                    st = self._create_label(
                        Foundation.NSMakeRect(box_w - 110, ry, 90, 18),
                        "Granted", 12, AppKit.NSFontWeightMedium, AppKit.NSColor.systemGreenColor())
                    st.setAlignment_(AppKit.NSTextAlignmentRight)
                    box.addSubview_(st)
                else:
                    btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 120, ry - 4, 104, 24))
                    btn.setTitle_("Open Settings")
                    btn.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
                    btn.setContentTintColor_(AppKit.NSColor.systemGreenColor())
                    btn.setTarget_(row["target"])
                    btn.setAction_(row["action"])
                    box.addSubview_(btn)

            # Separator between rows (not after last)
            if i < len(rows) - 1:
                sep_y = box_h - pad_top - row_h * (i + 1)
                box.addSubview_(self._create_separator(Foundation.NSMakeRect(pad_x, sep_y, box_w - pad_x * 2, 1)))

        content.addSubview_(box)
        return cy - box_h

    def build(self):
        # Layout constants
        width = 480
        margin = 24
        box_w = width - margin * 2
        section_gap = 28       # space between box bottom and next section header
        header_box_gap = 8     # space between section header and its box
        box_h = 100            # two-row box height

        # Compute total height top-down
        # titlebar(28) + top_pad(20) + status(40) + sep_gap(20)
        # + 3 × (header(20) + header_box_gap + box_h + section_gap) - last section_gap + bottom_pad(24)
        content_h = 28 + 20 + 40 + 20 + 3 * (20 + header_box_gap + box_h + section_gap) - section_gap + 24
        height = content_h

        screen_frame = AppKit.NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - width) / 2
        y = (screen_frame.size.height - height) / 2

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (width, height)),
            AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSFullSizeContentViewWindowMask,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Typeness")
        self.window.setTitlebarAppearsTransparent_(True)
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self.controller)

        content = AppKit.NSVisualEffectView.alloc().initWithFrame_(((0, 0), (width, height)))
        content.setMaterial_(AppKit.NSVisualEffectMaterialWindowBackground)
        content.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        content.setState_(AppKit.NSVisualEffectStateActive)
        self.window.setContentView_(content)

        cy = height - 48  # below titlebar
        box_w = width - margin * 2

        # ── Status header ──
        icon_img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("person.wave.2.fill", None)
        icon_view = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(margin, cy, 32, 32))
        icon_view.setImage_(icon_img)
        icon_view.setContentTintColor_(AppKit.NSColor.systemGreenColor())
        content.addSubview_(icon_view)

        title = self._create_label(Foundation.NSMakeRect(margin + 42, cy + 14, 200, 20), "Typeness", 16, AppKit.NSFontWeightSemibold)
        content.addSubview_(title)

        status_dot = self._create_label(Foundation.NSMakeRect(margin + 42, cy - 2, 10, 16), "●", 10, AppKit.NSFontWeightBold, AppKit.NSColor.systemGreenColor())
        status_text = self._create_label(Foundation.NSMakeRect(margin + 52, cy - 2, 100, 16), "Ready", 12, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        content.addSubview_(status_dot)
        content.addSubview_(status_text)

        cy -= 20
        content.addSubview_(self._create_separator(Foundation.NSMakeRect(margin, cy, box_w, 1)))
        cy -= 20

        # ── Visual Indicator ──
        self._create_section_header(content, margin, cy, box_w, "eye", "Visual Indicator")
        cy -= 20 + header_box_gap
        cy = self._add_two_row_box(content, cy, margin, box_w, [
            {"title": "Show visual indicator",
             "subtitle": "Display a central icon when Typeness is processing",
             "widget": "switch", "value": app_settings.show_floating_window,
             "target": self.controller, "action": "showFloatingChanged:"},
            {"title": "Confirm before inserting",
             "subtitle": "Review transcription before inserting at cursor",
             "widget": "switch", "value": app_settings.confirm_before_inserting,
             "target": self.controller, "action": "confirmInsertChanged:"},
        ])
        cy -= section_gap

        # ── Shortcuts ──
        self._create_section_header(content, margin, cy, box_w, "keyboard", "Shortcuts")
        cy -= 20 + header_box_gap
        cy = self._add_two_row_box(content, cy, margin, box_w, [
            {"title": "Push-to-talk",
             "subtitle": "Hold to record, release to transcribe",
             "widget": "shortcut", "setting_key": "shortcut_push_to_talk",
             "on_change": self.on_change},
            {"title": "Toggle mode",
             "subtitle": "Press to start/stop recording",
             "widget": "shortcut", "setting_key": "shortcut_toggle_mode",
             "on_change": self.on_change},
        ])
        cy -= section_gap

        # ── Permissions ──
        mic_granted = self._check_mic_permission()
        acc_granted = self._check_accessibility_permission()
        self._create_section_header(content, margin, cy, box_w, "shield.lefthalf.filled", "Permissions")
        cy -= 20 + header_box_gap
        cy = self._add_two_row_box(content, cy, margin, box_w, [
            {"title": "Microphone",
             "subtitle": "Required for voice recording",
             "widget": "status", "granted": mic_granted,
             "target": self.controller, "action": "openMicSettings:"},
            {"title": "Accessibility",
             "subtitle": "Required for text insertion",
             "widget": "status", "granted": acc_granted,
             "target": self.controller, "action": "openAccSettings:"},
        ])

    def show(self):
        if not self.window:
            self.build()
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
