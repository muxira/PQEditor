# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PQEditor
# Usage: pyinstaller pqeditor.spec
# Requires CPython (not PyPy) where PySide6 wheels are available.
# Build: python -m pip install pyinstaller "pqeditor[gui]" && pyinstaller pqeditor.spec

block_cipher = None

# Собираем все Qt плагины и ffmpeg для QtMultimedia (иначе видео без картинки как в логе qt.multimedia.ffmpeg)
try:
    from PyInstaller.utils.hooks import collect_all
    tmp_ret = collect_all('PySide6')
    _pyside_datas = tmp_ret[0]
    _pyside_binaries = tmp_ret[1]
    _pyside_hidden = tmp_ret[2]
except Exception:
    _pyside_datas, _pyside_binaries, _pyside_hidden = [], [], []

try:
    from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
    _qt_multimedia_datas = collect_data_files('PySide6', include_py_files=False)
except Exception:
    _qt_multimedia_datas = []

a = Analysis(
    ['src/pqeditor/__main__.py'],
    pathex=['src'],
    binaries=_pyside_binaries,
    datas=[('FORMAT.md', '.'), ('examples', 'examples'), ('icon.ico', '.'), ('icon_1024x1024.jpg', '.')] + _pyside_datas + _qt_multimedia_datas,
    hiddenimports=['pqeditor.model', 'pqeditor.io', 'pqeditor.app_state', 'pqeditor.ui.main_window', 'pqeditor.i18n', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets'] + _pyside_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PQEditor',
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
    icon='icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PQEditor',
)
