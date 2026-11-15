# -*- mode: python ; coding: utf-8 -*-
"""RPChatOverlay.spec — сборка одного exe-файла через PyInstaller.

Сборка (Windows, Python 3.12):
    pyinstaller --noconfirm --clean RPChatOverlay.spec
Результат: dist\\RPChatOverlay.exe (один файл, ничего дополнительно ставить не нужно).

Проще всего — запустить build_exe.bat: он сам создаст окружение, поставит
PyInstaller и соберёт exe.
"""
from PyInstaller.utils.hooks import collect_submodules

# динамические импорты (importlib) PyInstaller сам не видит — перечисляем явно
hidden = []
hidden += collect_submodules("langpacks")
hidden += collect_submodules("deep_translator")

excludes = [
    "tkinter", "unittest", "test", "pydoc_data", "sqlite3",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtSql",
    "numpy", "PIL", "pandas", "matplotlib", "scipy",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("icon.ico", ".")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RPChatOverlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # окно консоли не нужно, всё в logs\app.log
    disable_windowed_traceback=False,
    icon="icon.ico",
    # метаданные exe: «Свойства» -> «Подробнее». Меньше эвристических срабатываний
    # антивирусов, чем у файла без версии/издателя (см. version_info.txt).
    version="version_info.txt",
)
