"""Clipboard and text insertion module for Typeness.

Provides multiple ways to insert text:
- insert_text_at_cursor(): Uses Accessibility API to insert directly (no clipboard)
- paste_text(): Copies to clipboard and simulates Cmd+V (fallback)
- copy_to_clipboard(): Copies to clipboard only (for confirm-before-insert mode)
"""

import time

import pyperclip
from pynput.keyboard import Controller, Key


_keyboard = Controller()


def insert_text_at_cursor(text: str) -> bool:
    """Insert text at cursor position using macOS Accessibility API.

    This does NOT touch the clipboard. Returns True on success, False on failure.
    """
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementSetAttributeValue,
    )

    system = AXUIElementCreateSystemWide()
    err, focused = AXUIElementCopyAttributeValue(system, "AXFocusedUIElement", None)
    if err or not focused:
        print(f"[clipboard] AX: could not get focused element (err={err})")
        return False

    err = AXUIElementSetAttributeValue(focused, "AXSelectedText", text)
    if err:
        print(f"[clipboard] AX: could not set selected text (err={err})")
        return False

    return True


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard without pasting."""
    pyperclip.copy(text)


def paste_text(text: str) -> None:
    """Copy text to clipboard and simulate Cmd+V to paste it.

    A short delay between clipboard write and key simulation ensures
    the clipboard content is ready before pasting.
    """
    pyperclip.copy(text)
    time.sleep(0.02)

    _keyboard.press(Key.cmd)
    _keyboard.press("v")
    _keyboard.release("v")
    _keyboard.release(Key.cmd)
