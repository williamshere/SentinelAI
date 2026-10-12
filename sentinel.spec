# -*- mode: python ; coding: utf-8 -*-
"""
sentinel.spec - PyInstaller Build Specification for Sentinel AI.
Packages Sentinel AI into a standalone, production-ready Windows executable.
"""
from pathlib import Path
import os
import sys

block_cipher = None

# Base directory resolution
PROJECT_ROOT = Path(SPECPATH).resolve()

# Bundled data files
datas = [
    (str(PROJECT_ROOT / 'config.py'), '.'),
]

assets_dir = PROJECT_ROOT / 'assets'
if assets_dir.exists():
    datas.append((str(assets_dir), 'assets'))

# Hidden imports to ensure dynamic modules, Windows COM/WMI, and sensor APIs are bundled
hiddenimports = [
    # Qt6 / PySide6 Modules
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    
    # Windows native & COM APIs
    'win32com',
    'win32com.client',
    'win32api',
    'win32con',
    'win32gui',
    'win32process',
    'pythoncom',
    'wmi',
    
    # Hardware sensors & diagnostics
    'pynvml',
    'psutil',
    'sqlite3',
    'requests',
    'urllib3',
    'json',
    
    # Internal Sentinel AI packages
    'core',
    'core.autostart',
    'core.driver_manager',
    'core.game_mode',
    'ai',
    'ai.analyzer',
    'ai.chat_engine',
    'ai.health',
    'ai.predictive',
    'ai.prompts',
    'ai.recommendations',
    'database',
    'database.manager',
    'sensors',
    'sensors.cpu',
    'sensors.gpu',
    'sensors.ram',
    'sensors.disk',
    'sensors.storage_health',
    'ui',
    'ui.dashboard',
    'ui.alert_manager',
    'ui.chart_widget',
    'ui.theme',
]

a = Analysis(
    ['app.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy.distutils',
        'unittest',
        'test',
        'tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# Icon path resolution
icon_file = PROJECT_ROOT / 'assets' / 'sentinel.ico'
icon_path = str(icon_file) if icon_file.exists() else None

# Windowed Standalone Executable (console=False eliminates black cmd pop-up)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SentinelAI',
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
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SentinelAI',
)
