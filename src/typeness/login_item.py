"""macOS Login Item management for Typeness via launchd.

Installs/uninstalls a LaunchAgent plist so Typeness starts automatically at login.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

_PLIST_LABEL = "com.typeness.app"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"
_PROJECT_DIR = Path(__file__).resolve().parents[2]  # repo root: src/typeness/login_item.py -> src/typeness -> src -> repo


def is_installed() -> bool:
    return _PLIST_PATH.exists()


def _build_plist() -> str:
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
        args_xml = f"        <string>{exe_path}</string>"
    else:
        uv_path = shutil.which("uv")
        if uv_path is None:
            raise RuntimeError("uv not found in PATH. Please install uv first.")
        args_xml = f"""        <string>{uv_path}</string>
        <string>run</string>
        <string>--project</string>
        <string>{_PROJECT_DIR}</string>
        <string>typeness</string>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/Library/Logs/typeness.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/Library/Logs/typeness.log</string>
</dict>
</plist>
"""


def install() -> None:
    """Install and load the Typeness LaunchAgent."""
    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_PATH.write_text(_build_plist())

    # Unload first (ignore error if not loaded)
    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)],
                   capture_output=True)
    subprocess.run(["launchctl", "load", str(_PLIST_PATH)], check=True)

    print(f"Typeness will now start automatically at login.")
    print(f"Plist: {_PLIST_PATH}")
    print(f"Log:   ~/Library/Logs/typeness.log")


def uninstall() -> None:
    """Unload and remove the Typeness LaunchAgent."""
    if not _PLIST_PATH.exists():
        print("Typeness login item is not installed.")
        return

    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)],
                   capture_output=True)
    _PLIST_PATH.unlink()
    print("Typeness login item removed.")
