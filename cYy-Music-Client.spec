# -*- mode: python ; coding: utf-8 -*-

import os
import subprocess

APP_NAME = 'cYy-Music-Client_macos-arm64'
EXE_NAME = APP_NAME + '_bin'
ICON_PATH = 'icon.icns'

# ----- 查找 VLC -----
VLC_LIB_DIR = '/Applications/VLC.app/Contents/MacOS/lib'
VLC_PLUGINS_DIR = '/Applications/VLC.app/Contents/MacOS/plugins'
if not (os.path.exists(VLC_LIB_DIR) and os.path.exists(VLC_PLUGINS_DIR)):
    try:
        prefix = subprocess.check_output(['brew', '--prefix', 'vlc'], text=True).strip()
        if prefix:
            VLC_LIB_DIR = os.path.join(prefix, 'lib')
            VLC_PLUGINS_DIR = os.path.join(prefix, 'plugins')
    except:
        pass
if not (os.path.exists(VLC_LIB_DIR) and os.path.exists(VLC_PLUGINS_DIR)):
    raise RuntimeError('VLC not found.')

libvlc = os.path.join(VLC_LIB_DIR, 'libvlc.dylib')
libvlccore = os.path.join(VLC_LIB_DIR, 'libvlccore.dylib')
if not (os.path.exists(libvlc) and os.path.exists(libvlccore)):
    raise RuntimeError('VLC libs missing.')

# ----- 查找 ffmpeg -----
def find_ffmpeg():
    try:
        prefix = subprocess.check_output(['brew', '--prefix', 'ffmpeg'], text=True).strip()
        if prefix:
            return prefix
    except:
        pass
    for p in ['/usr/local/opt/ffmpeg', '/opt/homebrew/opt/ffmpeg']:
        if os.path.exists(p):
            return p
    raise RuntimeError('ffmpeg not found.')

FFMPEG_PREFIX = find_ffmpeg()
ffmpeg_bin = os.path.join(FFMPEG_PREFIX, 'bin')
ffmpeg_lib = os.path.join(FFMPEG_PREFIX, 'lib')
if not os.path.exists(os.path.join(ffmpeg_bin, 'ffmpeg')):
    raise RuntimeError('ffmpeg executable not found.')

# ----- 构建 datas -----
datas = [
    (libvlc, 'vlc'),
    (libvlccore, 'vlc'),
    (VLC_PLUGINS_DIR, 'vlc/plugins'),
    (ffmpeg_bin, 'ffmpeg/bin'),
    (ffmpeg_lib, 'ffmpeg/lib'),
]

# ----- 查找 portaudio -----
PORT_AUDIO_LIB = None
for p in ['/usr/local/lib/libportaudio.dylib', '/opt/homebrew/lib/libportaudio.dylib']:
    if os.path.exists(p):
        PORT_AUDIO_LIB = p
        break
if PORT_AUDIO_LIB:
    datas.append((PORT_AUDIO_LIB, 'ffmpeg/lib'))
else:
    print("Warning: libportaudio.dylib not found, sounddevice may fail.")

# ----- 分析 -----
a = Analysis(
    ['musicdlgui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name=EXE_NAME,
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
        'CFBundleShortVersionString': '4.1.0',
        'CFBundleVersion': '4.1.0',
        'CFBundleName': 'cYy Music Client',
        'CFBundleDisplayName': 'cYy Music Client',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13',
    },
)