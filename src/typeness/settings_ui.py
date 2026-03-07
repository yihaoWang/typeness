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

    def build(self):
        width = 480
        height = 580

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

        # Transparent visual effect background for modern look
        content = AppKit.NSVisualEffectView.alloc().initWithFrame_(((0,0), (width, height)))
        content.setMaterial_(AppKit.NSVisualEffectMaterialWindowBackground)
        content.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        content.setState_(AppKit.NSVisualEffectStateActive)
        self.window.setContentView_(content)

        cy = height - 60
        margin = 30
        box_w = width - margin*2

        # 1. Status Section
        icon_img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("person.wave.2.fill", None)
        icon_view = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(margin, cy, 32, 32))
        icon_view.setImage_(icon_img)
        icon_view.setContentTintColor_(AppKit.NSColor.systemGreenColor())
        content.addSubview_(icon_view)

        title = self._create_label(Foundation.NSMakeRect(margin+45, cy+14, 200, 20), "Typeness", 16, AppKit.NSFontWeightSemibold)
        content.addSubview_(title)

        status_dot = self._create_label(Foundation.NSMakeRect(margin+45, cy-2, 10, 16), "●", 10, AppKit.NSFontWeightBold, AppKit.NSColor.systemGreenColor())
        status_text = self._create_label(Foundation.NSMakeRect(margin+55, cy-2, 100, 16), "Ready", 12, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        content.addSubview_(status_dot)
        content.addSubview_(status_text)

        # 2. Visual Indicator Section
        cy -= 50
        lbl = self._create_label(Foundation.NSMakeRect(margin, cy, 200, 20), "􀏚  Visual Indicator", 13, AppKit.NSFontWeightSemibold)
        content.addSubview_(lbl)

        cy -= 110
        box1 = self._create_box(Foundation.NSMakeRect(margin, cy, box_w, 100))

        # Show visual indicator
        y = 65
        lbl1 = self._create_label(Foundation.NSMakeRect(16, y+10, 200, 20), "Show visual indicator", 13, AppKit.NSFontWeightMedium)
        lbl1_sub = self._create_label(Foundation.NSMakeRect(16, y-5, 300, 16), "Display a central icon when Typeness is processing", 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        box1.addSubview_(lbl1)
        box1.addSubview_(lbl1_sub)

        sw1 = AppKit.NSSwitch.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 60, y+5, 40, 24))
        sw1.setState_(AppKit.NSControlStateValueOn if app_settings.show_floating_window else AppKit.NSControlStateValueOff)
        sw1.setTarget_(self.controller)
        sw1.setAction_("showFloatingChanged:")
        box1.addSubview_(sw1)

        box1.addSubview_(self._create_separator(Foundation.NSMakeRect(16, y-15, box_w-32, 1)))

        # Confirm before inserting
        y = 5
        lbl3 = self._create_label(Foundation.NSMakeRect(16, y+10, 200, 20), "Confirm before inserting", 13, AppKit.NSFontWeightMedium)
        lbl3_sub = self._create_label(Foundation.NSMakeRect(16, y-5, 300, 16), "Review transcription before inserting at cursor", 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        box1.addSubview_(lbl3)
        box1.addSubview_(lbl3_sub)

        sw2 = AppKit.NSSwitch.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 60, y+10, 40, 24))
        sw2.setState_(AppKit.NSControlStateValueOn if app_settings.confirm_before_inserting else AppKit.NSControlStateValueOff)
        sw2.setTarget_(self.controller)
        sw2.setAction_("confirmInsertChanged:")
        box1.addSubview_(sw2)

        content.addSubview_(box1)

        # 3. Shortcuts Section
        cy -= 45
        lbl = self._create_label(Foundation.NSMakeRect(margin, cy, 200, 20), "􀇳  Shortcuts", 13, AppKit.NSFontWeightSemibold)
        content.addSubview_(lbl)

        cy -= 110
        box2 = self._create_box(Foundation.NSMakeRect(margin, cy, box_w, 100))

        y = 55
        lbl4 = self._create_label(Foundation.NSMakeRect(16, y+10, 200, 20), "Push-to-talk", 13, AppKit.NSFontWeightMedium)
        lbl4_sub = self._create_label(Foundation.NSMakeRect(16, y-5, 300, 16), "Hold to record, release to transcribe", 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        box2.addSubview_(lbl4)
        box2.addSubview_(lbl4_sub)

        btn_ptt = ShortcutButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 80, y+5, 64, 24))
        btn_ptt.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
        btn_ptt.setting_key = "shortcut_push_to_talk"
        btn_ptt.on_change = self.on_change
        btn_ptt._update_title()
        box2.addSubview_(btn_ptt)

        box2.addSubview_(self._create_separator(Foundation.NSMakeRect(16, y-15, box_w-32, 1)))

        y = 5
        lbl5 = self._create_label(Foundation.NSMakeRect(16, y+10, 200, 20), "Toggle mode", 13, AppKit.NSFontWeightMedium)
        lbl5_sub = self._create_label(Foundation.NSMakeRect(16, y-5, 300, 16), "Press to start/stop recording", 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        box2.addSubview_(lbl5)
        box2.addSubview_(lbl5_sub)

        btn_tog = ShortcutButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 80, y+5, 64, 24))
        btn_tog.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
        btn_tog.setting_key = "shortcut_toggle_mode"
        btn_tog.on_change = self.on_change
        btn_tog._update_title()
        box2.addSubview_(btn_tog)

        content.addSubview_(box2)

        # 4. Permissions Section
        cy -= 45
        lbl = self._create_label(Foundation.NSMakeRect(margin, cy, 200, 20), "􀢒  Permissions", 13, AppKit.NSFontWeightSemibold)
        content.addSubview_(lbl)

        cy -= 110
        box3 = self._create_box(Foundation.NSMakeRect(margin, cy, box_w, 100))

        y = 55
        lbl6 = self._create_label(Foundation.NSMakeRect(16, y+10, 200, 20), "Microphone", 13, AppKit.NSFontWeightMedium)
        lbl6_sub = self._create_label(Foundation.NSMakeRect(16, y-5, 300, 16), "Required for voice recording", 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        box3.addSubview_(lbl6)
        box3.addSubview_(lbl6_sub)

        btn_mic = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 120, y+5, 104, 24))
        btn_mic.setTitle_("Open Settings")
        btn_mic.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
        btn_mic.setTarget_(self.controller)
        btn_mic.setAction_("openMicSettings:")
        box3.addSubview_(btn_mic)

        box3.addSubview_(self._create_separator(Foundation.NSMakeRect(16, y-15, box_w-32, 1)))

        y = 5
        lbl7 = self._create_label(Foundation.NSMakeRect(16, y+10, 200, 20), "Accessibility", 13, AppKit.NSFontWeightMedium)
        lbl7_sub = self._create_label(Foundation.NSMakeRect(16, y-5, 300, 16), "Required for global shortcuts and text insertion", 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        box3.addSubview_(lbl7)
        box3.addSubview_(lbl7_sub)

        btn_acc = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 120, y+5, 104, 24))
        btn_acc.setTitle_("Open Settings")
        btn_acc.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
        btn_acc.setTarget_(self.controller)
        btn_acc.setAction_("openAccSettings:")
        box3.addSubview_(btn_acc)

        content.addSubview_(box3)

    def show(self):
        if not self.window:
            self.build()
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
