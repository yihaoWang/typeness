# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['src/typeness/__main__.py'],
    pathex=[],
    binaries=[('/Users/yihao.wang/project/typeness/.venv/lib/python3.12/site-packages/mlx/lib/*.metallib', 'mlx/lib')],
    datas=[('/Users/yihao.wang/project/typeness/.venv/lib/python3.12/site-packages/mlx_whisper/assets/*', 'mlx_whisper/assets')],
    hiddenimports=collect_submodules('mlx') + collect_submodules('mlx_lm'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Typeness',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Typeness',
)
app = BUNDLE(
    coll,
    name='Typeness.app',
    icon='icon.icns',
    bundle_identifier='com.typeness.app',
    info_plist={
        'LSUIElement': True,
        'NSMicrophoneUsageDescription': 'Typeness requires microphone access to record voice input.',
        'NSAppleEventsUsageDescription': 'Typeness requires system access to paste transcribed text.',
        'NSSystemAdministrationUsageDescription': 'Typeness requires access to register global hotkeys.',
    },
)
