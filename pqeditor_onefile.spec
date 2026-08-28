# -*- mode: python ; coding: utf-8 -*-
# One-file minimal build for sharing — English default UI + icon + ffmpeg
# Usage: pyinstaller --clean --noconfirm pqeditor_onefile.spec
# Result: dist/PQEditor.exe (~90-120MB with ffmpeg, UPX if installed)
import sys
from pathlib import Path

block_cipher = None

# Собираем только нужные Qt модули, исключаем тяжёлые
excludes = [
    'PySide6.Qt3DAnimation','PySide6.Qt3DCore','PySide6.Qt3DExtras','PySide6.Qt3DInput','PySide6.Qt3DLogic','PySide6.Qt3DRender',
    'PySide6.QtCharts','PySide6.QtDataVisualization','PySide6.QtGraphs','PySide6.QtGraphsWidgets',
    'PySide6.QtHelp','PySide6.QtHttpServer','PySide6.QtLocation','PySide6.QtPositioning',
    'PySide6.QtPdf','PySide6.QtPdfWidgets','PySide6.QtQuick','PySide6.QtQml','PySide6.QtQuick3D','PySide6.QtQuickControls2','PySide6.QtQuickWidgets',
    'PySide6.QtRemoteObjects','PySide6.QtScxml','PySide6.QtSensors','PySide6.QtSerialBus','PySide6.QtSerialPort','PySide6.QtSpatialAudio',
    'PySide6.QtSql','PySide6.QtStateMachine','PySide6.QtTest','PySide6.QtTextToSpeech','PySide6.QtWebChannel','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtWebSockets','PySide6.QtWebView',
    'PySide6.QtDesigner','PySide6.QtBluetooth','PySide6.QtNfc','PySide6.QtOpenGL','PySide6.QtOpenGLWidgets',
]

# datas/binaries — только нужное
try:
    from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
    # multimedia plugins + platforms
    _datas = collect_data_files('PySide6', include_py_files=False, excludes=['**/qml','**/translations','**/Qt3D*','**/QtWeb*'])
    _binaries = collect_dynamic_libs('PySide6')
except Exception:
    _datas, _binaries = [], []

a = Analysis(
    ['src/pqeditor/__main__.py'],
    pathex=['src'],
    binaries=_binaries,
    datas=[('FORMAT.md', '.'), ('examples', 'examples'), ('icon.ico', '.'), ('icon_1024x1024.jpg', '.')] + _datas,
    hiddenimports=[
        'pqeditor.model','pqeditor.io','pqeditor.app_state','pqeditor.ui.main_window','pqeditor.i18n',
        'PySide6.QtCore','PySide6.QtGui','PySide6.QtWidgets','PySide6.QtMultimedia','PySide6.QtMultimediaWidgets','PySide6.QtNetwork',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# убираем лишние из Analysis (если всё равно собрались)
a.datas = [d for d in a.datas if 'Qt3D' not in str(d[0]) and 'QtWeb' not in str(d[0]) and 'QtQml' not in str(d[0])]
a.binaries = [b for b in a.binaries if 'Qt3D' not in b[0] and 'QtWebEngine' not in b[0]]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PQEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
