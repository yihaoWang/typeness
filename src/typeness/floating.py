import AppKit
import objc
import Quartz

class FloatingWindowController:
    def __init__(self):
        self.window = None
        self._create_window()

    def _create_window(self):
        # Create a borderless, transparent window for the central icon
        rect = AppKit.NSMakeRect(0, 0, 80, 80)
        style = AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel
        self.window = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            style,
            AppKit.NSBackingStoreBuffered,
            False
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setIgnoresMouseEvents_(True)
        self.window.setLevel_(AppKit.NSPopUpMenuWindowLevel)
        self.window.setHasShadow_(True)
        self.window.setFloatingPanel_(True)
        self.window.setHidesOnDeactivate_(False)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
            AppKit.NSWindowCollectionBehaviorIgnoresCycle
        )

        # Create the visual effect view (blur background)
        visual_effect_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(rect)
        visual_effect_view.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
        visual_effect_view.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        visual_effect_view.setState_(AppKit.NSVisualEffectStateActive)

        # Add rounded corners
        visual_effect_view.setWantsLayer_(True)
        visual_effect_view.layer().setCornerRadius_(20.0)
        visual_effect_view.layer().setMasksToBounds_(True)

        # Create icon view
        self.icon_view = AppKit.NSImageView.alloc().initWithFrame_(AppKit.NSMakeRect(16, 16, 48, 48))
        self.icon_view.setContentTintColor_(AppKit.NSColor.labelColor())

        visual_effect_view.addSubview_(self.icon_view)
        self.window.setContentView_(visual_effect_view)

    def show(self, sf_symbol_name: str):
        from typeness.settings import app_settings
        if not app_settings.show_floating_window:
            return

        # Capture mouse position NOW before queuing to the main thread.
        captured_loc = AppKit.NSEvent.mouseLocation()

        @objc.python_method
        def _do_show():
            # Set the SF Symbol image
            config = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
                36, AppKit.NSFontWeightRegular, AppKit.NSImageSymbolScaleMedium
            )
            img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(sf_symbol_name, None)
            if img:
                img = img.imageWithSymbolConfiguration_(config)
                img.setTemplate_(True)
                self.icon_view.setImage_(img)

            # Find which screen the mouse was on
            target_screen = AppKit.NSScreen.mainScreen()
            for screen in AppKit.NSScreen.screens():
                f = screen.frame()
                if (f.origin.x <= captured_loc.x < f.origin.x + f.size.width and
                        f.origin.y <= captured_loc.y < f.origin.y + f.size.height):
                    target_screen = screen
                    break

            # DEBUG: print screen detection info
            print(f"[floating] mouse=({captured_loc.x:.0f}, {captured_loc.y:.0f})")
            for i, s in enumerate(AppKit.NSScreen.screens()):
                f = s.frame()
                print(f"[floating]   screen[{i}]: origin=({f.origin.x:.0f}, {f.origin.y:.0f}) size=({f.size.width:.0f}x{f.size.height:.0f})")
            tf = target_screen.frame()
            print(f"[floating]   target: origin=({tf.origin.x:.0f}, {tf.origin.y:.0f})")

            # Center on target screen
            screen_rect = target_screen.visibleFrame()
            x = screen_rect.origin.x + (screen_rect.size.width - 80) / 2
            y = screen_rect.origin.y + (screen_rect.size.height - 80) / 2
            target_rect = AppKit.NSMakeRect(x, y, 80, 80)

            # Force window to move to the active space by cycling visibility
            self.window.orderOut_(None)
            self.window.setFrame_display_(target_rect, True)
            self.window.orderFrontRegardless()

            # DEBUG: verify final position
            final = self.window.frame()
            print(f"[floating]   final frame: origin=({final.origin.x:.0f}, {final.origin.y:.0f})")

        AppKit.CFRunLoopPerformBlock(
            AppKit.CFRunLoopGetMain(),
            AppKit.kCFRunLoopCommonModes,
            _do_show
        )
        AppKit.CFRunLoopWakeUp(AppKit.CFRunLoopGetMain())

    def hide(self):
        @objc.python_method
        def _do_hide():
            self.window.orderOut_(None)

        AppKit.CFRunLoopPerformBlock(
            AppKit.CFRunLoopGetMain(),
            AppKit.kCFRunLoopCommonModes,
            _do_hide
        )
        AppKit.CFRunLoopWakeUp(AppKit.CFRunLoopGetMain())

_shared_floating_window = None

def init_floating_window():
    global _shared_floating_window
    if _shared_floating_window is None:
        _shared_floating_window = FloatingWindowController()

def show_floating_state(state: str):
    if _shared_floating_window is None:
        return

    if state == "recording":
        _shared_floating_window.hide()
    elif state == "transcribing":
        _shared_floating_window.show("waveform")
    elif state == "processing":
        _shared_floating_window.show("sparkles")
    elif state == "done":
        _shared_floating_window.hide()
    else:
        _shared_floating_window.hide()
