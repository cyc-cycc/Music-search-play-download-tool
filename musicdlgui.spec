# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

APP_NAME = 'Music-spd-tool_macos-arm64'
ICON_PATH = 'icon.icns'

# ----- 自动检测 VLC 安装路径 -----
def find_vlc_prefix():
    # 优先从环境变量获取
    prefix = os.environ.get('VLC_PREFIX')
    if prefix and os.path.exists(prefix):
        return prefix

    # 检查常见的安装位置
    candidates = [
        '/Applications/VLC.app/Contents/MacOS',   # Cask 安装
        '/usr/local/opt/vlc',                    # Homebrew 核心（可能已废弃）
        '/usr/local/opt/vlc/lib',                # 如果是 Homebrew 的 lib 目录
    ]
    for cand in candidates:
        if os.path.exists(cand):
            # 如果是 /usr/local/opt/vlc，则 lib 在下面，需要调整
            if cand.endswith('/vlc'):
                # 检查 lib 子目录是否存在
                libdir = os.path.join(cand, 'lib')
                if os.path.exists(libdir):
                    return libdir
            else:
                # 直接检查有没有 libvlc.dylib
                if os.path.exists(os.path.join(cand, 'libvlc.dylib')):
                    return cand
                # 检查 lib 子目录
                libdir = os.path.join(cand, 'lib')
                if os.path.exists(os.path.join(libdir, 'libvlc.dylib')):
                    return libdir
    raise RuntimeError('VLC not found. Please install VLC and set VLC_PREFIX environment variable.')

VLC_PREFIX = find_vlc_prefix()
print(f'Using VLC from: {VLC_PREFIX}')

# VLC 文件位置
libvlc = os.path.join(VLC_PREFIX, 'libvlc.dylib')
libvlccore = os.path.join(VLC_PREFIX, 'libvlccore.dylib')
plugins = os.path.join(VLC_PREFIX, 'plugins')

# 如果上面路径不存在，尝试在 VLC_PREFIX 下查找
if not os.path.exists(libvlc):
    # 可能库在 VLC_PREFIX/ 而不是 VLC_PREFIX/lib/
    libvlc = os.path.join(os.path.dirname(VLC_PREFIX), 'libvlc.dylib')
    libvlccore = os.path.join(os.path.dirname(VLC_PREFIX), 'libvlccore.dylib')
    plugins = os.path.join(os.path.dirname(VLC_PREFIX), 'plugins')
    if not os.path.exists(libvlc) or not os.path.exists(libvlccore) or not os.path.isdir(plugins):
        raise RuntimeError(f'VLC files not found in {VLC_PREFIX}')

# 打印确认
print(f'libvlc: {libvlc}, plugins: {plugins}')

# ----- 分析 -----
a = Analysis(
    ['musicdlgui.py'],
    pathex=[],
    binaries=[],
    datas=[
        (libvlc, 'vlc'),
        (libvlccore, 'vlc'),
        (plugins, 'vlc/plugins'),
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
    [],
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
    icon=ICON_PATH,
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