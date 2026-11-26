# -*- mode: python ; coding: utf-8 -*-
"""FiveMChatOverlay.spec — сборка одного exe-файла через PyInstaller.

Собирает source/main.py вместе с пакетом source/app (модули программы,
словари языков, интерфейс) в один FiveMChatOverlay.exe.
Bundles source/main.py together with the source/app package (program modules,
language packs, interface) into a single FiveMChatOverlay.exe.

Сборка (Windows, Python 3.12):
    pyinstaller --noconfirm --clean FiveMChatOverlay.spec
Результат: dist\\FiveMChatOverlay.exe (один файл, ничего дополнительно ставить не нужно).

Проще всего — запустить build_exe.bat: он сам создаст окружение, поставит
PyInstaller и соберёт exe.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def _submodules(package):
    """Подмодули пакета; пакета нет — пусто, сборка не падает.

    The submodules of a package; an absent package gives an empty list so the
    build never fails over an optional dependency.
    """
    try:
        return collect_submodules(package)
    except Exception:
        print(f"[spec] {package} не установлен — собираю без него")
        return []


def _data(package):
    """Файлы данных пакета; пакета нет — пусто / the data files of a package."""
    try:
        return collect_data_files(package)
    except Exception:
        return []


# Динамические импорты PyInstaller сам не видит — перечисляем явно.
# collect_submodules рекурсивно обходит новые доменные подпакеты (включая
# app.animations.settings) и сохраняет совместимость старых фасадов.
# PyInstaller cannot see dynamic imports; collect_submodules recursively walks
# domain subpackages (including app.animations.settings) and legacy facades.
hidden = []
hidden += collect_submodules("app")
hidden += collect_submodules("app.langpacks")
# Словарь словоформ для уровня «Леммы». Если пакет не установлен, exe соберётся
# без словаря: уровень «Леммы» откатится к основам, программа работает.
# The word-form dictionary for the "Lemmas" level. Without the package the exe
# is built without it: the level falls back to stems and the program still works.
hidden += _submodules("pymorphy3")
hidden += _submodules("pymorphy3_dicts_ru")
dictionary_data = _data("pymorphy3_dicts_ru") + _data("pymorphy3")

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
    datas=[("icon.ico", ".")] + dictionary_data,
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
    name="FiveMChatOverlay",
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
