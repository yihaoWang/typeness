#!/bin/bash
set -e

echo "Ensuring pyinstaller is installed..."
uv add --dev pyinstaller

echo "Building Typeness.app with PyInstaller..."
uv run pyinstaller --noconfirm Typeness.spec

echo "Build complete! The app is located at dist/Typeness.app"
