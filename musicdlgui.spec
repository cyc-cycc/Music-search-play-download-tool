# -*- mode: python ; coding: utf-8 -*-

import os
import subprocess

APP_NAME = 'Music-spd-tool_macos-arm64'
ICON_PATH = 'icon.icns'   # 如果不存在，自动忽略

# ----- 硬编码 VLC 路径（GitHub Actions 实测路径） -----
VLC_LIB_DIR = '/Applications/VLC.app/Contents/MacOS/lib'
VLC_PLUGINS_DIR = '/Applications/VLC.app/Contents/MacOS/plugins'

# 如果上面路径不存在，尝试通过 brew 获取
if not (os.path.exists(VLC_LIB_DIR) and os.path.exists(VLC_PLUGINS_DIR)):
    try:
        prefix = subprocess.check_output(['brew', '--prefix', 'vlc'], text=True).strip()
        if prefix:
            VLC_LIB_DIR = os.path.join(prefix, 'lib')
            VLC_PLUGINS_DIR = os.path.join(prefix, 'plugins')
    except Exception:
        pass

if not (os.path.exists(VLC_LIB_DIR) and os.path.exists(VLC_PLUGINS_DIR)):
    raise RuntimeError('VLC library or plugins not found.')

libvlc = os.path.join(VLC_LIB_DIR, 'libvlc.dylib')
libvlccore = os.path.join(VLC_LIB_DIR, 'libvlccore.dylib')
if not (os.path.exists(libvlc) and os.path.exists(libvlccore)):
    raise RuntimeError('libvlc.dylib or libvlccore.dylib not found.')

# ----- 分析 -----
a = Analysis(
    ['musicdlgui.py'],
    pathex=[],
    binaries=[],
    datas=[
        (libvlc, 'vlc'),
        (libvlccore, 'vlc'),
        (VLC_PLUGINS_DIR, 'vlc/plugins'),
    ],
    hiddenimports=[
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

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
)

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
    icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
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