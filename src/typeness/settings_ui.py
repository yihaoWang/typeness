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
        box.setBorderType_(AppKit.NSNoBorder)
        box.setCornerRadius_(8.0)
        box.setContentViewMargins_(Foundation.NSMakeSize(0, 0))
        box.setFillColor_(AppKit.NSColor.controlBackgroundColor())
        return box

    def _create_separator(self, frame):
        sep = AppKit.NSBox.alloc().initWithFrame_(frame)
        sep.setBoxType_(AppKit.NSBoxCustom)
        sep.setBorderType_(AppKit.NSNoBorder)
        sep.setFillColor_(AppKit.NSColor.separatorColor().colorWithAlphaComponent_(0.5))
        return sep

    def _create_section_header(self, content, x, y, box_w, title, height=16):
        """Create a section header with uppercase label. y is the bottom edge."""
        lbl = self._create_label(Foundation.NSMakeRect(x + 16, y, 200, height), title.upper(), 11, AppKit.NSFontWeightSemibold, AppKit.NSColor.secondaryLabelColor())
        content.addSubview_(lbl)

    def _create_colored_icon(self, frame, sf_symbol, bg_color):
        """Create an iOS-style settings icon (white symbol on colored rounded rect)."""
        box = AppKit.NSBox.alloc().initWithFrame_(frame)
        box.setBoxType_(AppKit.NSBoxCustom)
        box.setBorderType_(AppKit.NSNoBorder)
        box.setCornerRadius_(6.0)
        box.setFillColor_(bg_color)

        # Draw the SF symbol centered in the container
        img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(sf_symbol, None)
        if img:
            conf = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(14, AppKit.NSFontWeightSemibold, AppKit.NSImageSymbolScaleMedium)
            img = img.imageByApplyingSymbolConfiguration_(conf) if hasattr(img, 'imageByApplyingSymbolConfiguration_') else img.imageWithSymbolConfiguration_(conf) if hasattr(img, 'imageWithSymbolConfiguration_') else img
            iv = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, frame.size.width, frame.size.height))
            iv.setImage_(img)
            iv.setContentTintColor_(AppKit.NSColor.whiteColor())
            box.addSubview_(iv)

        return box

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

    def _add_settings_group(self, content, y, margin, box_w, box_h, rows):
        """Create a rounded box with rows of content at the specified Y (bottom edge).

        Each row is a dict with keys: title, subtitle, icon, icon_color, and one of:
          widget='switch', value=bool, target=obj, action=str
          widget='shortcut', setting_key=str, on_change=callable
          widget='status', granted=bool, target=obj, action=str
        """
        row_h = 52
        pad_x = 16
        icon_size = 28
        icon_margin_right = 16

        box = self._create_box(Foundation.NSMakeRect(margin, y, box_w, box_h))

        for i, row in enumerate(rows):
            ry = box_h - row_h * (i + 1)

            # Left side: colored icon
            icon_x = pad_x
            icon_y = ry + (row_h - icon_size) / 2
            icon_view = self._create_colored_icon(
                Foundation.NSMakeRect(icon_x, icon_y, icon_size, icon_size),
                row["icon"], row["icon_color"]
            )
            box.addSubview_(icon_view)

            text_x = icon_x + icon_size + icon_margin_right

            # Subtitle check
            if row.get("subtitle"):
                # Title + subtitle vertically stacked
                lbl = self._create_label(
                    Foundation.NSMakeRect(text_x, ry + row_h/2, box_w - text_x - 120, 18),
                    row["title"], 13, AppKit.NSFontWeightMedium)
                sub = self._create_label(
                    Foundation.NSMakeRect(text_x, ry + row_h/2 - 16, box_w - text_x - 120, 15),
                    row["subtitle"], 11, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
                box.addSubview_(lbl)
                box.addSubview_(sub)
            else:
                # Just title vertically centered
                lbl = self._create_label(
                    Foundation.NSMakeRect(text_x, ry + (row_h - 18)/2, box_w - text_x - 120, 18),
                    row["title"], 13, AppKit.NSFontWeightMedium)
                box.addSubview_(lbl)

            # Right-side widget
            w = row.get("widget")
            if w == "switch":
                sw = AppKit.NSSwitch.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 60, ry + (row_h - 24)/2, 40, 24))
                sw.setState_(AppKit.NSControlStateValueOn if row["value"] else AppKit.NSControlStateValueOff)
                sw.setTarget_(row["target"])
                sw.setAction_(row["action"])
                box.addSubview_(sw)
            elif w == "shortcut":
                btn = ShortcutButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 96, ry + (row_h - 24)/2, 80, 24))
                btn.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
                btn.setting_key = row["setting_key"]
                btn.on_change = row["on_change"]
                btn._update_title()
                box.addSubview_(btn)
            elif w == "status":
                if row["granted"]:
                    st = self._create_label(
                        Foundation.NSMakeRect(box_w - 110, ry + (row_h - 18)/2, 94, 18),
                        "Granted", 13, AppKit.NSFontWeightRegular, AppKit.NSColor.systemGreenColor())
                    st.setAlignment_(AppKit.NSTextAlignmentRight)
                    box.addSubview_(st)
                else:
                    btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(box_w - 120, ry + (row_h - 24)/2, 104, 24))
                    btn.setTitle_("Open Settings")
                    btn.setBezelStyle_(AppKit.NSRoundRectBezelStyle)
                    btn.setContentTintColor_(AppKit.NSColor.systemGreenColor())
                    btn.setTarget_(row["target"])
                    btn.setAction_(row["action"])
                    box.addSubview_(btn)

            # Separator between rows (not after last)
            if i < len(rows) - 1:
                sep_y = ry
                box.addSubview_(self._create_separator(Foundation.NSMakeRect(text_x, sep_y, box_w - text_x, 1)))

        content.addSubview_(box)

    def build(self):
        # Layout constants
        width = 460
        margin = 32
        box_w = width - margin * 2
        
        section_lbl_h = 16
        header_box_gap = 6     # space between section header bottom and box top
        section_gap = 24       # space between box bottom and next section header top
        
        box_1_h = 52 * 2
        box_2_h = 52 * 2
        box_3_h = 52 * 2

        # Header components vertical sizes
        top_margin = 32
        icon_size = 64
        status_gap = 32
        
        header_h = top_margin + icon_size + status_gap

        # Compute total height top-down
        content_h = header_h + \
            (section_lbl_h + header_box_gap + box_1_h) + section_gap + \
            (section_lbl_h + header_box_gap + box_2_h) + section_gap + \
            (section_lbl_h + header_box_gap + box_3_h) + 32
            
        height = content_h

        screen_frame = AppKit.NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - width) / 2
        # Position slightly higher than center
        y = (screen_frame.size.height - height) / 2 + 50

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (width, height)),
            AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSFullSizeContentViewWindowMask,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Settings")
        self.window.setTitlebarAppearsTransparent_(True)
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self.controller)

        content = AppKit.NSVisualEffectView.alloc().initWithFrame_(((0, 0), (width, height)))
        content.setMaterial_(AppKit.NSVisualEffectMaterialWindowBackground)
        content.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        content.setState_(AppKit.NSVisualEffectStateActive)
        self.window.setContentView_(content)

        # Coordinate `cy` represents the bottom edge of the next element drawn top-down
        cy = height

        # ── Status header ──
        cy -= top_margin
        
        cy -= icon_size
        header_y = cy
        
        import os
        import sys
        
        icon_path = None
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, "icon.icns")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "icon.icns")
            
        icon_img = None
        if icon_path and os.path.exists(icon_path):
            icon_img = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
            
        if not icon_img:
            icon_img = AppKit.NSApplication.sharedApplication().applicationIconImage()
            
        if not icon_img:
            icon_img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("macwindow", None)
            
        header_content_w = 64 + 16 + 120  # icon + gap + text
        start_x = margin
            
        icon_view = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(start_x, header_y, icon_size, icon_size))
        icon_view.setImage_(icon_img)
        content.addSubview_(icon_view)
        
        text_x = start_x + icon_size + 16
        
        # Text block is 28 (title) + 4 (gap) + 20 (status) = 52. 
        # Center in 64 height icon: (64-52)/2 = 6 pad
        status_y = header_y + 6
        title_y = status_y + 20 + 4
        
        title = self._create_label(Foundation.NSMakeRect(text_x, title_y, 120, 28), "Typeness", 20, AppKit.NSFontWeightBold)
        title.setAlignment_(AppKit.NSTextAlignmentLeft)
        content.addSubview_(title)
        
        status_container = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(text_x, status_y, 100, 20))
        status_dot = self._create_label(Foundation.NSMakeRect(0, 2, 12, 16), "●", 10, AppKit.NSFontWeightBold, AppKit.NSColor.systemGreenColor())
        status_text = self._create_label(Foundation.NSMakeRect(14, 2, 60, 16), "Ready", 13, AppKit.NSFontWeightMedium, AppKit.NSColor.secondaryLabelColor())
        status_container.addSubview_(status_dot)
        status_container.addSubview_(status_text)
        content.addSubview_(status_container)
        
        cy -= status_gap

        # ── Visual Indicator ──
        cy -= section_lbl_h
        self._create_section_header(content, margin, cy, box_w, "Visual Indicator", height=section_lbl_h)
        cy -= header_box_gap
        cy -= box_1_h
        self._add_settings_group(content, cy, margin, box_w, box_1_h, [
            {"title": "Show visual indicator",
             "subtitle": "Display a central icon when processing",
             "icon": "eye.fill", "icon_color": AppKit.NSColor.systemBlueColor(),
             "widget": "switch", "value": app_settings.show_floating_window,
             "target": self.controller, "action": "showFloatingChanged:"},
            {"title": "Confirm before inserting",
             "subtitle": "Review transcription before inserting",
             "icon": "text.badge.checkmark", "icon_color": AppKit.NSColor.systemGreenColor(),
             "widget": "switch", "value": app_settings.confirm_before_inserting,
             "target": self.controller, "action": "confirmInsertChanged:"},
        ])

        # ── Shortcuts ──
        cy -= section_gap
        cy -= section_lbl_h
        self._create_section_header(content, margin, cy, box_w, "Shortcuts", height=section_lbl_h)
        cy -= header_box_gap
        cy -= box_2_h
        self._add_settings_group(content, cy, margin, box_w, box_2_h, [
            {"title": "Push-to-talk",
             "subtitle": "Hold to record, release to transcribe",
             "icon": "mic.fill", "icon_color": AppKit.NSColor.systemRedColor(),
             "widget": "shortcut", "setting_key": "shortcut_push_to_talk",
             "on_change": self.on_change},
            {"title": "Toggle mode",
             "subtitle": "Press to start/stop recording",
             "icon": "keyboard.fill", "icon_color": AppKit.NSColor.systemPurpleColor(),
             "widget": "shortcut", "setting_key": "shortcut_toggle_mode",
             "on_change": self.on_change},
        ])

        # ── Permissions ──
        mic_granted = self._check_mic_permission()
        acc_granted = self._check_accessibility_permission()
        
        cy -= section_gap
        cy -= section_lbl_h
        self._create_section_header(content, margin, cy, box_w, "Permissions", height=section_lbl_h)
        cy -= header_box_gap
        cy -= box_3_h
        self._add_settings_group(content, cy, margin, box_w, box_3_h, [
            {"title": "Microphone",
             "subtitle": "Required for voice recording",
             "icon": "mic.fill", "icon_color": AppKit.NSColor.systemOrangeColor(),
             "widget": "status", "granted": mic_granted,
             "target": self.controller, "action": "openMicSettings:"},
            {"title": "Accessibility",
             "subtitle": "Required for text insertion",
             "icon": "figure.stand", "icon_color": AppKit.NSColor.systemBlueColor(),
             "widget": "status", "granted": acc_granted,
             "target": self.controller, "action": "openAccSettings:"},
        ])

    def show(self):
        if not self.window:
            self.build()
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
