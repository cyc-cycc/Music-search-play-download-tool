# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# ---------- 配置 ----------
APP_NAME = 'Music-spd-tool_macos-arm64'
ICON_PATH = 'icon.icns'  # 请确保图标文件存在

# VLC 相关路径（通过 brew 获取，若在 GitHub Actions 中可环境变量传入）
# 建议在构建前通过 `export VLC_PREFIX=$(brew --prefix vlc)` 传入
VLC_PREFIX = os.environ.get('VLC_PREFIX', '/usr/local/opt/vlc')
if not os.path.exists(VLC_PREFIX):
    # 如果路径不存在，尝试默认 Homebrew 路径
    VLC_PREFIX = '/usr/local/opt/vlc'

# ---------- 分析对象 ----------
a = Analysis(
    ['musicdlgui.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 将 VLC 库和插件整体作为数据目录复制到 app 内部的 vlc/ 子目录
        (os.path.join(VLC_PREFIX, 'lib'), 'vlc/lib'),
        (os.path.join(VLC_PREFIX, 'plugins'), 'vlc/plugins'),
    ],
    hiddenimports=[
        # 必要隐藏导入（涵盖你的依赖）
        'matplotlib.backends.backend_qt5agg',
        'numba',
        'sklearn.utils._cython_blas',
        'scipy.special._cdflib',
        'scipy.linalg.cython_blas',
        'scipy.linalg.cython_lapack',
        'sounddevice',
        'librosa',
        'numpy',
        'mutagen',
        'requests',
        'filetype',
        'musicdl',
        'vlc',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ---------- 可执行文件 ----------
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # 不显示终端窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)

# ---------- macOS 应用包 ----------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=APP_NAME + '.app',
    icon=ICON_PATH,
    bundle_identifier='com.yourcompany.musicdlgui',
    info_plist={
        'CFBundleShortVersionString': '4.0.0',
        'CFBundleVersion': '4.0.0',
        'CFBundleName': 'Music Downloader',
        'CFBundleDisplayName': 'Music Downloader',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13',
    },
)