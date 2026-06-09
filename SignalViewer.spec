# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — SignalViewer

  用法: pyinstaller SignalViewer.spec
  输出: dist/SignalViewer/SignalViewer.exe
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('logo.ico', '.')],        # 把 logo.ico 打包到 exe 同目录
    hiddenimports=[
        'scipy.io',
        'h5py',
        'numpy',
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'pyqtgraph.Qt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SignalViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # 不显示命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',            # exe 图标
)
