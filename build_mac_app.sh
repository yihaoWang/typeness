#!/bin/bash
set -e

echo "Ensuring pyinstaller is installed..."
uv add --dev pyinstaller

echo "Building Typeness.app with PyInstaller..."
uv run pyinstaller --noconfirm Typeness.spec

echo "Applying explicit ad-hoc deep code signature to satisfy macOS TCC..."
xattr -cr dist/Typeness.app 2>/dev/null || true
codesign --force --deep --sign - dist/Typeness.app

echo "Build complete! The app is located at dist/Typeness.app"
