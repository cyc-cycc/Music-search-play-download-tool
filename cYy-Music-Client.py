# -*- coding: utf-8 -*-
import os
import sys
def setup_runtime_paths():
    """在源码或打包环境下，自动定位 VLC 和 FFmpeg 并设置环境变量（支持 Windows / macOS）"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    # ---------- VLC ----------
    vlc_dir = None
    candidates = [
        base,
        os.path.join(base, 'vlc'),
        os.path.join(base, 'VLC'),
    ]
    # 如果打包时放在当前目录下
    if os.path.exists(os.path.join(base, 'libvlc.dll')) or os.path.exists(os.path.join(base, 'libvlc.dylib')):
        candidates.append(base)

    for cand in candidates:
        if sys.platform == 'win32':
            if os.path.isdir(cand) and os.path.exists(os.path.join(cand, 'libvlc.dll')):
                vlc_dir = cand
                break
        else:  # macOS / Linux
            if os.path.isdir(cand) and (os.path.exists(os.path.join(cand, 'libvlc.dylib')) or
                                        os.path.exists(os.path.join(cand, 'libvlc.so'))):
                vlc_dir = cand
                break

    # macOS 下如果没找到，尝试系统安装的 VLC
    if vlc_dir is None and sys.platform == 'darwin':
        # 常见路径：/Applications/VLC.app/Contents/MacOS/lib
        vlc_app_lib = '/Applications/VLC.app/Contents/MacOS/lib'
        if os.path.exists(os.path.join(vlc_app_lib, 'libvlc.dylib')):
            vlc_dir = vlc_app_lib
        else:
            # 尝试通过 brew 查找
            try:
                import subprocess
                prefix = subprocess.check_output(['brew', '--prefix', 'vlc'], text=True).strip()
                vlc_brew_lib = os.path.join(prefix, 'lib')
                if os.path.exists(os.path.join(vlc_brew_lib, 'libvlc.dylib')):
                    vlc_dir = vlc_brew_lib
            except Exception:
                pass

    if vlc_dir:
        # Windows 直接加入 PATH
        if sys.platform == 'win32':
            os.environ['PATH'] = vlc_dir + os.pathsep + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(vlc_dir)
                except Exception:
                    pass
            plugin_dir = os.path.join(vlc_dir, 'plugins')
            if os.path.isdir(plugin_dir):
                os.environ['VLC_PLUGIN_PATH'] = plugin_dir
        else:
            # macOS：设置动态库搜索路径
            # 注意：macOS SIP 可能限制 DYLD_LIBRARY_PATH，使用 DYLD_FALLBACK_LIBRARY_PATH 更安全
            lib_path = os.environ.get('DYLD_FALLBACK_LIBRARY_PATH', '')
            if lib_path:
                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = vlc_dir + os.pathsep + lib_path
            else:
                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = vlc_dir

            # 设置插件路径（如果存在 plugins 子目录）
            plugin_dir = os.path.join(vlc_dir, 'plugins')
            if not os.path.isdir(plugin_dir):
                # 尝试 ../plugins（当 vlc_dir 是 lib 时）
                parent = os.path.dirname(vlc_dir)
                if os.path.isdir(os.path.join(parent, 'plugins')):
                    plugin_dir = os.path.join(parent, 'plugins')
            if os.path.isdir(plugin_dir):
                os.environ['VLC_PLUGIN_PATH'] = plugin_dir

    # ---------- FFmpeg ----------
    ffmpeg_bin = None
    ffmpeg_lib = None
    # 在 base 下查找 ffmpeg/bin
    for cand in [os.path.join(base, 'ffmpeg', 'bin'), os.path.join(base, 'ffmpeg')]:
        if os.path.isdir(cand):
            if sys.platform == 'win32':
                if os.path.exists(os.path.join(cand, 'ffmpeg.exe')):
                    ffmpeg_bin = cand
                    ffmpeg_lib = os.path.join(os.path.dirname(cand), 'lib') if os.path.isdir(os.path.join(os.path.dirname(cand), 'lib')) else None
                    break
            else:
                if os.path.exists(os.path.join(cand, 'ffmpeg')):
                    ffmpeg_bin = cand
                    ffmpeg_lib = os.path.join(os.path.dirname(cand), 'lib') if os.path.isdir(os.path.join(os.path.dirname(cand), 'lib')) else None
                    break

    # macOS 下如果没找到，尝试系统 ffmpeg（brew）
    if ffmpeg_bin is None and sys.platform == 'darwin':
        try:
            import subprocess
            prefix = subprocess.check_output(['brew', '--prefix', 'ffmpeg'], text=True).strip()
            brew_bin = os.path.join(prefix, 'bin')
            brew_lib = os.path.join(prefix, 'lib')
            if os.path.exists(os.path.join(brew_bin, 'ffmpeg')):
                ffmpeg_bin = brew_bin
                ffmpeg_lib = brew_lib
        except Exception:
            pass

    if ffmpeg_bin:
        # 将 bin 目录加入 PATH
        os.environ['PATH'] = ffmpeg_bin + os.pathsep + os.environ.get('PATH', '')
        ffmpeg_exe = os.path.join(ffmpeg_bin, 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
        if os.path.exists(ffmpeg_exe):
            os.environ['AUDIOREAD_FFMPEG'] = ffmpeg_exe
        # 如果有 lib 目录，也加入动态库路径（macOS）
        if ffmpeg_lib and sys.platform == 'darwin':
            lib_path = os.environ.get('DYLD_FALLBACK_LIBRARY_PATH', '')
            if lib_path:
                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = ffmpeg_lib + os.pathsep + lib_path
            else:
                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = ffmpeg_lib

setup_runtime_paths()

import re
from enum import IntEnum
import logging
import threading
import traceback
import glob
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Callable, Tuple
from logging.handlers import RotatingFileHandler

from mutagen.id3 import ID3, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture
import librosa
import numpy as np
import sounddevice as sd

import requests
import filetype
from PyQt5 import QtCore
from PyQt5.QtGui import (
    QIcon, QFont, QPixmap, QColor, QMouseEvent,
    QPainter, QBrush, QPen, QPalette, QDesktopServices
)
from PyQt5.QtCore import (
    QThread, pyqtSignal, Qt, QTimer, QObject,
    QRunnable, QThreadPool, pyqtSlot, QPoint, QRect,
    QRectF, QUrl
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QCheckBox, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QGridLayout,
    QProgressBar, QMenu, QMessageBox, QAbstractItemView,
    QSpinBox, QHeaderView, QFileDialog, QComboBox, QHBoxLayout,
    QVBoxLayout, QGroupBox, QSizePolicy, QSlider, QListWidget,
    QListWidgetItem, QProgressDialog, QMainWindow, QFrame,
    QSplitter, QDialog, QTabWidget, QFormLayout
)

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

import vlc

from musicdl import musicdl
from musicdl.modules.utils.misc import IOUtils, sanitize_filepath


# ==================== 常量 ====================
SOURCE_GROUPS = {
    '国内音乐': [
        'QQ音乐(高质量无损,推荐)',
        '网易云音乐(高质量无损)',
        '酷我音乐(普通无损,推荐)',
        '酷狗音乐(普通无损)',
        '咪咕音乐(普通音质,推荐)',
        '5sing音乐'
    ],
    '国外音乐': [
        'SoundCloud(for XuiS😍)',
    ]
}

SOURCE_INTERNAL = {
    '网易云音乐(高质量无损)': 'NeteaseMusicClient',
    'QQ音乐(高质量无损,推荐)': 'QQMusicClient',
    '酷我音乐(普通无损,推荐)': 'KuwoMusicClient',
    '酷狗音乐(普通无损)': 'KugouMusicClient',
    '咪咕音乐(普通音质,推荐)': 'MiguMusicClient',
    'SoundCloud(for XuiS😍)': 'SoundCloudMusicClient',
    '5sing音乐': 'FiveSingMusicClient',
}

FILENAME_FORMATS = ['歌曲名', '歌手-歌曲名', '歌曲名-歌手', '自定义']

PLAYLIST_SOURCE_MAP = {
    '网易云音乐': 'NeteaseMusicClient',
    'QQ音乐': 'QQMusicClient',
    '酷我音乐': 'KuwoMusicClient',
    '酷狗音乐': 'KugouMusicClient',
    '5sing音乐': 'FiveSingMusicClient',
}

APP_DIR = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable)
if sys.platform == 'darwin':
    DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "musicspdgui-cyy")
else:
    DATA_DIR = APP_DIR
LOG_DIR = os.path.join(DATA_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'musicdl_gui.log')
DEFAULT_SAVE_DIR = os.path.join(DATA_DIR, 'download')

try:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(DEFAULT_SAVE_DIR, exist_ok=True)
except Exception as e:
    print(f"警告：无法创建数据目录：{e}")

logger = logging.getLogger('MusicdlGUI')
logger.setLevel(logging.DEBUG)
logger.propagate = False

file_handler = None
try:
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.ERROR if os.getenv('MUSICDL_GUI_DEBUG') is None else logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
except Exception as e:
    print(f"警告：无法创建日志文件 {LOG_FILE}：{e}")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.ERROR if os.getenv('MUSICDL_GUI_DEBUG') is None else logging.DEBUG)
console_handler.setFormatter(file_formatter)
logger.addHandler(console_handler)

# ==================== 工具函数 ====================
def _download_image_data(
    url: str,
    request_kwargs: Dict,
    max_size: int = 5 * 1024 * 1024,
    session: Optional[requests.Session] = None
) -> Tuple[Optional[bytes], Optional[str]]:
    if not url:
        return None, None
    try:
        sess = session or requests.Session()
        kw = request_kwargs.copy()
        kw['timeout'] = kw.get('timeout', 10)
        kw['stream'] = True
        kw.pop('data', None)
        kw.pop('json', None)

        with sess.get(url, **kw) as resp:
            if resp.status_code != 200:
                return None, None
            content_length = resp.headers.get('content-length')
            if content_length and int(content_length) > max_size:
                logger.warning(f"封面图片过大 ({content_length} bytes)，跳过下载")
                return None, None
            data = b''
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                data += chunk
                if len(data) > max_size:
                    logger.warning("封面数据超过限制，截断")
                    return None, None
            if not data:
                return None, None

            kind = filetype.guess(data)
            if kind and kind.extension in ('jpg', 'jpeg', 'png', 'bmp', 'gif'):
                ext = kind.extension
                if ext == 'jpeg':
                    ext = 'jpg'
                return data, ext
            else:
                content_type = resp.headers.get('content-type', '').lower()
                if 'png' in content_type:
                    return data, 'png'
                elif 'jpeg' in content_type or 'jpg' in content_type:
                    return data, 'jpg'
                else:
                    logger.warning(f"未知图片格式: {content_type}")
                    return None, None
    except Exception as e:
        logger.error(f"图片下载异常: {e}", exc_info=True)
        return None, None

def get_cover_url(song_info: Dict) -> Optional[str]:
    for key in ['cover_url', 'cover', 'song_cover', 'album_cover', 'pic_url', 'img_url']:
        val = song_info.get(key)
        if val:
            return val
    return None

def download_cover_image(url: str, request_kwargs: Dict, max_size: int = 5 * 1024 * 1024) -> Tuple[Optional[bytes], Optional[str]]:
    return _download_image_data(url, request_kwargs, max_size, session=None)

# ==================== 异常钩子 ====================
def global_exception_hook(exctype, value, tb):
    error_msg = ''.join(traceback.format_exception(exctype, value, tb))
    logger.error(error_msg)
    try:
        app = QApplication.instance()
        if app:
            main_widget = app.activeWindow()
            if main_widget and hasattr(main_widget, 'label_stats'):
                QTimer.singleShot(0, lambda: main_widget.label_stats.setText(
                    f'⚠️ 程序发生错误，详见日志文件: {LOG_FILE}'
                ))
    except Exception:
        pass
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_hook

# ==================== 播放器封装 ====================
class PlayerState(IntEnum):
    StoppedState = 0
    PlayingState = 1
    PausedState = 2

class PlayerMediaStatus(IntEnum):
    UnknownMediaStatus = 0
    NoMedia = 1
    LoadingMedia = 2
    LoadedMedia = 3
    BufferingMedia = 4
    BufferedMedia = 5
    EndOfMedia = 6
    InvalidMedia = 7

class PlayMode(IntEnum):
    SingleRepeat = 0
    SingleStop = 1
    ListRepeat = 2
    ListStop = 3

class PlayerWrapper(QObject):
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    stateChanged = pyqtSignal(PlayerState)
    mediaStatusChanged = pyqtSignal(PlayerMediaStatus)

    def __init__(self, parent=None):
        super().__init__(parent)
        vlc_log = os.path.join(DATA_DIR, 'vlc.log')
        vlc_args = ['--verbose=0', f'--logfile={vlc_log}']
        plugin_path = os.environ.get('VLC_PLUGIN_PATH')
        if plugin_path:
            vlc_args.append(f'--plugin-path={plugin_path}')
        self._instance = vlc.Instance(*vlc_args)
        self._player = self._instance.media_player_new()
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_position)
        self._timer.setInterval(200)
        self._duration = 0
        self._current_media = None

    def setMedia(self, url: str, headers: dict = None):
        self._current_media = self._instance.media_new(url)
        self._current_media.add_option(':network-caching=3000')
        if headers:
            header_items = [f'{k}={v}' for k, v in headers.items() if v is not None]
            if header_items:
                self._current_media.add_option(f':http-header={":".join(header_items)}')
        self._player.set_media(self._current_media)
        self._duration = 0
        self.durationChanged.emit(0)
        self.mediaStatusChanged.emit(PlayerMediaStatus.LoadedMedia)

    def play(self, volume=None):
        self._player.play()
        self._timer.start()
        self.stateChanged.emit(PlayerState.PlayingState)
        if volume is not None:
            QTimer.singleShot(500, lambda: self._player.audio_set_volume(volume))

    def pause(self):
        self._player.pause()
        self.stateChanged.emit(PlayerState.PausedState)

    def stop(self):
        self._player.stop()
        self._timer.stop()
        self.positionChanged.emit(0)
        self.stateChanged.emit(PlayerState.StoppedState)

    def setPosition(self, pos_ms: int):
        self._player.set_time(pos_ms)

    def position(self) -> int:
        return self._player.get_time()

    def duration(self) -> int:
        return self._player.get_length()

    def setVolume(self, vol: int):
        self._player.audio_set_volume(vol)

    def volume(self) -> int:
        return self._player.audio_get_volume()

    def state(self) -> PlayerState:
        state = self._player.get_state()
        if state == vlc.State.Playing:
            return PlayerState.PlayingState
        elif state == vlc.State.Paused:
            return PlayerState.PausedState
        else:
            return PlayerState.StoppedState

    def mediaStatus(self) -> PlayerMediaStatus:
        state = self._player.get_state()
        if state in (vlc.State.Ended, vlc.State.Stopped):
            return PlayerMediaStatus.EndOfMedia
        elif state == vlc.State.Playing:
            return PlayerMediaStatus.LoadedMedia
        else:
            return PlayerMediaStatus.LoadedMedia

    def _update_position(self):
        try:
            pos = self._player.get_time()
            if pos >= 0:
                self.positionChanged.emit(pos)
            dur = self._player.get_length()
            if dur != self._duration and dur > 0:
                self._duration = dur
                self.durationChanged.emit(dur)
            state = self._player.get_state()
            if state == vlc.State.Ended:
                self._timer.stop()
                self.mediaStatusChanged.emit(PlayerMediaStatus.EndOfMedia)
                self.stateChanged.emit(PlayerState.StoppedState)
        except Exception as e:
            logger.error(f"VLC 位置更新异常: {e}", exc_info=True)

    def reset(self):
        self.stop()
        self._player = self._instance.media_player_new()
        self._duration = 0
        self._current_media = None
        self.durationChanged.emit(0)

# ==================== 封面下载 ====================
class CoverRunnableSignals(QObject):
    finished = pyqtSignal(object)

class CoverRunnable(QRunnable):
    def __init__(self, url: str, request_kwargs: Dict, task_id: int, session: Optional[requests.Session] = None, max_size: int = 5 * 1024 * 1024):
        super().__init__()
        self.url = url
        self.request_kwargs = request_kwargs.copy() if request_kwargs else {}
        self.task_id = task_id
        self.signals = CoverRunnableSignals()
        self._session = session
        self._max_size = max_size

    @pyqtSlot()
    def run(self):
        data, ext = _download_image_data(self.url, self.request_kwargs, self._max_size, self._session)
        if data:
            self.signals.finished.emit((data, self.task_id))
        else:
            self.signals.finished.emit((b'', self.task_id))

# ==================== 搜索线程 ====================
class SearchThread(QThread):
    source_started = pyqtSignal(str)
    source_finished = pyqtSignal(str, list)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, music_client: musicdl.MusicClient, sources: List[str],
                 keyword: str, limit_per_source: int, threadings_per_source: int = 5):
        super().__init__()
        self.music_client = music_client
        self.sources = sources
        self.keyword = keyword
        self.limit_per_source = limit_per_source
        self.threadings_per_source = threadings_per_source
        self._stop_event = threading.Event()
        self._executor = None

    def stop(self):
        self._stop_event.set()
        if self._executor:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass

    def run(self):
        self._executor = ThreadPoolExecutor(max_workers=max(1, len(self.sources)))
        futures = {}
        try:
            for source in self.sources:
                if self._stop_event.is_set():
                    break
                self.source_started.emit(source)
                fut = self._executor.submit(
                    self._search_single_source, source, self.keyword,
                    self.limit_per_source, self.threadings_per_source
                )
                futures[fut] = source

            for fut in concurrent.futures.as_completed(futures):
                if self._stop_event.is_set():
                    break
                source = futures.get(fut)
                try:
                    results = fut.result()
                    if results is None:
                        results = []
                    self.source_finished.emit(source, results)
                except Exception as e:
                    self.error.emit(f"{source} 搜索失败: {str(e)}")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass
            self.finished.emit()

    def _search_single_source(self, source: str, keyword: str, limit: int,
                              num_threadings: int) -> Optional[List]:
        if self._stop_event.is_set():
            return None
        try:
            client = self.music_client.music_clients[source]
            results = client.search(
                keyword=keyword,
                num_threadings=num_threadings
            )
            return results[:limit]
        except Exception as e:
            raise e

# ==================== 歌单解析线程 ====================
class PlaylistParseThread(QThread):
    parse_started = pyqtSignal()
    parse_finished = pyqtSignal(list, str)
    parse_error = pyqtSignal(str)

    def __init__(self, playlist_url: str, source_internal: str, source_display: str):
        super().__init__()
        self.playlist_url = playlist_url
        self.source_internal = source_internal
        self.source_display = source_display
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self.parse_started.emit()
            init_cfg = {self.source_internal: {'search_size_per_source': 50}}
            client = musicdl.MusicClient(
                music_sources=[self.source_internal],
                init_music_clients_cfg=init_cfg
            )
            if self._stop:
                return
            song_infos = client.parseplaylist(self.playlist_url)
            if self._stop:
                return
            if not song_infos:
                self.parse_error.emit("歌单解析结果为空")
                return
            valid = []
            for info in song_infos:
                if self._stop:
                    return
                info['source'] = self.source_internal
                if not info.get('download_url'):
                    if info.get('url'):
                        info['download_url'] = info['url']
                    else:
                        logger.warning(f"歌曲 {info.get('song_name')} 缺少下载链接，跳过")
                        continue
                valid.append(info)
            if not valid:
                self.parse_error.emit("所有歌曲均无有效下载链接")
                return
            self.parse_finished.emit(valid, self.source_display)
        except Exception as e:
            logger.error(f"歌单解析线程异常: {e}", exc_info=True)
            self.parse_error.emit(str(e))

# ==================== 下载线程 ====================
class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, str, str)
    error = pyqtSignal(str)

    def __init__(self, song_info: Dict, get_request_kwargs: Callable[[str], Dict],
                 save_dir: str, filename_format: str,
                 download_lyric: bool, download_cover: bool):
        super().__init__()
        self.song_info = song_info
        self.get_request_kwargs = get_request_kwargs
        self.save_dir = save_dir
        self.filename_format = filename_format
        self.download_lyric = download_lyric
        self.download_cover = download_cover
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            source = self.song_info.get('source', '')
            url = self.song_info['download_url']
            work_dir = self.save_dir
            song_name = self.song_info.get('song_name', '')
            singers = self.song_info.get('singers', '')
            ext = self.song_info.get('ext', 'mp3') or 'mp3'

            base_name = self._build_base_name(song_name, singers)
            base_name = sanitize_filepath(base_name)
            IOUtils.touchdir(work_dir)

            audio_file_path = os.path.join(work_dir, f"{base_name}.{ext}")
            audio_file_path = self._get_unique_path(audio_file_path)

            request_kwargs = self.get_request_kwargs(source)
            if 'cookies' not in request_kwargs and self.song_info.get('cookies'):
                request_kwargs['cookies'] = self.song_info['cookies']

            self._download_file(url, audio_file_path, request_kwargs)

            if self.download_lyric and not self._stop:
                lyric_text = self.song_info.get('lyric') or self.song_info.get('lyrics', '')
                if lyric_text:
                    lyric_path = os.path.join(work_dir, f"{base_name}.lrc")
                    lyric_path = self._get_unique_path(lyric_path)
                    try:
                        with open(lyric_path, 'w', encoding='utf-8-sig') as f:
                            f.write(lyric_text)
                    except Exception as e:
                        logger.error(f"歌词保存失败: {e}", exc_info=True)
                        self.error.emit(f"歌词保存失败: {str(e)}")

            if self.download_cover and not self._stop:
                cover_url = get_cover_url(self.song_info)
                if cover_url:
                    img_data, cover_ext = download_cover_image(cover_url, request_kwargs)
                    if img_data:
                        cover_path = os.path.join(work_dir, f"{base_name}_cover.{cover_ext}")
                        cover_path = self._get_unique_path(cover_path)
                        try:
                            with open(cover_path, 'wb') as f:
                                f.write(img_data)
                            self._embed_cover(audio_file_path, img_data, cover_ext)
                        except Exception as e:
                            logger.error(f"保存/嵌入封面失败: {e}", exc_info=True)
                            self.error.emit(f"保存/嵌入封面失败: {str(e)}")

            if not self._stop:
                self.finished.emit(song_name, singers, audio_file_path)

        except Exception as e:
            logger.error(f"下载失败: {traceback.format_exc()}")
            self.error.emit(str(e))

    def _build_base_name(self, song_name: str, singers: str) -> str:
        fmt = self.filename_format
        if fmt == "歌曲名":
            return song_name
        elif fmt == "歌手-歌曲名":
            return f"{singers}-{song_name}"
        elif fmt == "歌曲名-歌手":
            return f"{song_name}-{singers}"
        else:
            template = fmt
            template = template.replace("{歌手}", singers)
            template = template.replace("{歌曲名}", song_name)
            template = template.replace("{专辑}", self.song_info.get('album', ''))
            template = template.replace("{时长}", self.song_info.get('duration', ''))
            return template

    def _get_unique_path(self, path: str) -> str:
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        counter = 1
        while True:
            new_path = f"{base}({counter}){ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def _download_file(self, url: str, file_path: str, request_kwargs: Dict):
        f = None
        session = None
        try:
            session = requests.Session()
            session.verify = request_kwargs.get('verify', True)
            headers = request_kwargs.get('headers') or {}
            session.headers.update(headers)
            cookies = request_kwargs.get('cookies') or {}
            if cookies:
                session.cookies.update(cookies)

            kw = {}
            kw.update({k: v for k, v in request_kwargs.items() if k in ('timeout', 'proxies', 'verify')})
            kw['stream'] = True
            timeout = kw.get('timeout', 30)

            with session.get(url, timeout=timeout, stream=True, **({} if 'proxies' not in kw else {'proxies': kw.get('proxies')})) as resp:
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")
                total_hdr = resp.headers.get('content-length')
                total = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
                downloaded = 0
                f = open(file_path, 'wb')
                last_emit_time = 0.0
                chunk_size = 32 * 1024
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if self._stop:
                        break
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if total:
                        percent = int(downloaded / total * 100)
                    else:
                        percent = min(99, int(downloaded / 1024))
                    if (now - last_emit_time) > 0.25 or percent == 100:
                        try:
                            self.progress.emit(percent)
                        except Exception:
                            pass
                        last_emit_time = now
                if self._stop:
                    try:
                        f.close()
                    except Exception:
                        pass
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception:
                            logger.error(f"清理临时文件失败: {file_path}")
                    raise Exception("下载已取消")
                self.progress.emit(100)
        except Exception as e:
            if f:
                try:
                    f.close()
                except Exception:
                    pass
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    logger.error(f"清理临时文件失败: {file_path}")
            raise e
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            if f and not f.closed:
                try:
                    f.close()
                except Exception:
                    pass

    def _embed_cover(self, audio_path: str, img_data: bytes, cover_ext: str):
        try:
            ext_lower = os.path.splitext(audio_path)[1].lower()
            if ext_lower == '.mp3':
                try:
                    audio = ID3(audio_path)
                except Exception:
                    audio = ID3()
                audio.add(APIC(
                    encoding=3,
                    mime=f'image/{cover_ext}',
                    type=3,
                    desc='Cover',
                    data=img_data
                ))
                audio.save(audio_path)
            elif ext_lower in ['.m4a', '.m4b']:
                audio = MP4(audio_path)
                if cover_ext.lower() == 'png':
                    cover_format = MP4Cover.FORMAT_PNG
                else:
                    cover_format = MP4Cover.FORMAT_JPEG
                audio['covr'] = [MP4Cover(img_data, imageformat=cover_format)]
                audio.save()
            elif ext_lower == '.flac':
                pic = Picture()
                pic.data = img_data
                pic.type = 3
                pic.mime = f'image/{cover_ext}'
                audio = FLAC(audio_path)
                audio.add_picture(pic)
                audio.save()
        except Exception as e:
            logger.error(f"嵌入封面失败: {e}", exc_info=True)
            try:
                self.error.emit(f"嵌入封面失败: {str(e)}")
            except Exception:
                pass

# ==================== 可视化窗口 ====================
class AudioVisualizer(QMainWindow):
    def __init__(self, audio_path: str = None, lyric_path: str = None,
                 cover_path: str = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("🎵 音频可视化")
        self.setGeometry(100, 100, 800, 700)
        self.setMinimumSize(700, 700)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.audio_data = None
        self.sample_rate = None
        self.read_index = 0
        self.lock = threading.Lock()
        self.paused = False
        self.volume = 0.6
        self.stream = None
        self.lyrics = []
        self.current_lyric_index = -1
        self.total_time = 0
        self.is_dragging = False

        self.fft_bins = 45
        self.ring_bins = 40
        self.y_max = 1.1
        self.smooth_alpha = 0.4
        self.smooth_bar_vals = None
        self.smooth_ring_vals = None

        self.norm_stft = None
        self.frame_count = 0
        self.frames_per_second = 0.0

        self.cover_path = cover_path

        self.drag_pos = QPoint()
        self.dragging = False

        self.signals = UpdateSignals()
        self.signals.update_ui.connect(self._update_ui)
        self.timer = QTimer()
        self.timer.timeout.connect(self.signals.update_ui.emit)
        self.timer.start(30)

        self._init_ui()

        if audio_path and os.path.exists(audio_path):
            self.load_audio(audio_path, lyric_path, cover_path)

    def _init_ui(self):
        central = QFrame()
        central.setStyleSheet("background: #F5F7FA; border-radius: 8px;")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(
            "background: #E8F0FE; border-bottom: 1px solid #BDC3C7;"
            "border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = self._title_mouse_release

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)
        title_layout.setSpacing(5)

        title_label = QLabel("🎵 音频可视化")
        title_label.setStyleSheet("color: #2C3E50; font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        for symbol, slot in [("—", self.showMinimized), ("□", self._toggle_maximize), ("✕", self.close)]:
            btn = QPushButton(symbol)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: #2C3E50; border: none; border-radius: 4px; font-size: 16px; }"
                "QPushButton:hover { background: #D5D8DC; }"
            )
            if symbol == "✕":
                btn.setStyleSheet(btn.styleSheet() + "QPushButton:hover { background: #E74C3C; color: white; }")
            btn.clicked.connect(slot)
            title_layout.addWidget(btn)
            if symbol == "□":
                self.max_btn = btn

        main_layout.addWidget(title_bar)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(
            "background: transparent; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;"
        )
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        self.bg_label = QLabel(self.content_widget)
        self.bg_label.setScaledContents(True)
        self.bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bg_label.hide()
        self.bg_label.setGeometry(self.content_widget.rect())

        splitter = QSplitter(Qt.Horizontal)
        content_layout.addWidget(splitter, 1)

        left_widget = QWidget()
        left_widget.setStyleSheet("background: rgba(255,255,255,0.8); border-radius: 8px;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(5)

        self.song_title_label = QLabel("未选择歌曲")
        self.song_title_label.setAlignment(Qt.AlignCenter)
        self.song_title_label.setFixedHeight(35)
        self.song_title_label.setStyleSheet(
            "background: transparent; color: #2C3E50; font-weight: bold; font-size: 16px; padding: 5px;"
        )
        left_layout.addWidget(self.song_title_label)

        self.lyric_list = QListWidget()
        self.lyric_list.setSelectionMode(QListWidget.NoSelection)
        self.lyric_list.setWordWrap(True)
        self.lyric_list.setFont(QFont("Microsoft YaHei", 11))
        self.lyric_list.setStyleSheet(
            "QListWidget { background: transparent; color: #2C3E50; border: none; }"
            "QListWidget::item { padding: 2px 5px; }"
        )
        left_layout.addWidget(self.lyric_list, 1)

        self.bar_fig = Figure(figsize=(6, 3), dpi=100, facecolor='none')
        self.bar_ax = self.bar_fig.add_subplot(111)
        self.bar_ax.set_facecolor('none')
        self.bar_ax.set_ylim(0, self.y_max)
        self.bar_ax.set_xticks([])
        self.bar_ax.set_yticks([])
        for spine in self.bar_ax.spines.values():
            spine.set_visible(False)
        self.bar_rects = self.bar_ax.bar(range(self.fft_bins), np.zeros(self.fft_bins),
                                         width=0.8, color='#4A90D9', edgecolor='none')
        self.bar_fig.tight_layout(pad=0)
        self.bar_canvas = FigureCanvas(self.bar_fig)
        self.bar_canvas.setStyleSheet("background: transparent; border: none;")
        left_layout.addWidget(self.bar_canvas, 1)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_widget.setStyleSheet("background: rgba(255,255,255,0.8); border-radius: 8px;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(5)

        self.ring_fig = Figure(figsize=(4, 4), dpi=100, facecolor='none')
        self.ring_ax = self.ring_fig.add_subplot(111, projection='polar')
        self.ring_ax.set_facecolor('none')
        self.ring_ax.set_ylim(0, self.y_max)
        self.ring_ax.set_xticks([])
        self.ring_ax.set_yticks([])
        self.ring_ax.spines['polar'].set_visible(False)
        self.ring_ax.grid(False)
        self.ring_angles = np.linspace(0, 2 * np.pi, self.ring_bins, endpoint=False)
        self.ring_lines = []
        self.ring_dots = []
        for angle in self.ring_angles:
            line, = self.ring_ax.plot([angle, angle], [0, 0], color='#4A90D9', linewidth=2, alpha=0.8)
            self.ring_lines.append(line)
            dot = self.ring_ax.scatter(angle, 0, s=10, color='#4A90D9', alpha=0.9, zorder=5)
            self.ring_dots.append(dot)
        self.ring_fig.tight_layout(pad=0)
        self.ring_canvas = FigureCanvas(self.ring_fig)
        self.ring_canvas.setStyleSheet("background: transparent; border: none;")
        right_layout.addWidget(self.ring_canvas)
        splitter.addWidget(right_widget)
        splitter.setSizes([550, 350])

        control = QWidget()
        control.setStyleSheet("background: rgba(255,255,255,0.8); border-radius: 8px; padding: 5px;")
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(10, 5, 10, 5)
        control_layout.setSpacing(10)

        self.select_btn = self._make_btn("📂 选择文件", self._select_file)
        control_layout.addWidget(self.select_btn)

        self.pause_btn = self._make_btn("⏸ 暂停", self._toggle_pause)
        self.pause_btn.setEnabled(False)
        control_layout.addWidget(self.pause_btn)

        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setValue(0)
        self.progress_slider.sliderPressed.connect(self._progress_press)
        self.progress_slider.sliderReleased.connect(self._progress_release)
        self.progress_slider.valueChanged.connect(self._progress_changed)
        self.progress_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 6px; background: #D5D8DC; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #4A90D9; width: 16px; margin: -5px 0; border-radius: 8px; }"
            "QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4A90D9, stop:1 #7B2FFC); border-radius: 3px; }"
        )
        control_layout.addWidget(self.progress_slider, 1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #2C3E50; font-size: 13px;")
        control_layout.addWidget(self.time_label)

        control_layout.addWidget(QLabel("🔊"))

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(60)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self._volume_change)
        self.volume_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #D5D8DC; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #4A90D9; width: 12px; margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4A90D9, stop:1 #7B2FFC); border-radius: 2px; }"
        )
        control_layout.addWidget(self.volume_slider)

        content_layout.addWidget(control, 0)
        main_layout.addWidget(self.content_widget)

        self.smooth_bar_vals = np.zeros(self.fft_bins)
        self.smooth_ring_vals = np.zeros(self.ring_bins)

    def _make_btn(self, text, slot):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.clicked.connect(slot)
        btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.8); color: #2C3E50; border: 1px solid #BDC3C7; border-radius: 4px; padding: 5px 12px; font-weight: bold; }"
            "QPushButton:hover { background: #E8F0FE; border-color: #4A90D9; }"
            "QPushButton:pressed { background: rgba(255,255,255,0.5); }"
            "QPushButton:disabled { color: #BDC3C7; border-color: #D5D8DC; }"
        )
        return btn

    def _title_mouse_press(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_pos = e.globalPos()
            self.dragging = True
            e.accept()

    def _title_mouse_move(self, e):
        if self.dragging:
            self.move(self.pos() + e.globalPos() - self.drag_pos)
            self.drag_pos = e.globalPos()
            e.accept()

    def _title_mouse_release(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            e.accept()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("□")
        else:
            self.showMaximized()
            self.max_btn.setText("❐")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'bg_label'):
            self.bg_label.setGeometry(self.content_widget.rect())
            self.bg_label.lower()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'bg_label') and self.cover_path:
            self.bg_label.setGeometry(self.content_widget.rect())
            self.bg_label.lower()

    def _set_cover_background(self, image_path):
        if image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self.bg_label.setPixmap(pixmap)
                self.bg_label.show()
                self.bg_label.setGeometry(self.content_widget.rect())
                return
        self.bg_label.hide()
        self.bg_label.clear()

    def load_audio(self, audio_path, lyric_path=None, cover_path=None):
        if not os.path.exists(audio_path):
            return
        try:
            data, sr = librosa.load(audio_path, sr=None, mono=True)
            self.audio_data = data.astype(np.float32)
            self.sample_rate = sr
            self.read_index = 0
            self.paused = False
            self.pause_btn.setText("⏸ 暂停")
            self.pause_btn.setEnabled(True)

            hop_length = 512
            n_fft = 2048
            D = librosa.stft(self.audio_data, n_fft=n_fft, hop_length=hop_length)
            mag = np.abs(D)
            mel_basis = librosa.filters.mel(sr=sr, n_fft=n_fft, n_mels=self.fft_bins)
            mel_spec = np.dot(mel_basis, mag)
            log_mel = np.log1p(mel_spec)
            col_max = np.max(log_mel, axis=0)
            col_max[col_max == 0] = 1.0
            self.norm_stft = (log_mel / col_max[np.newaxis, :]).clip(0.0, 1.0).astype(np.float32)
            self.frame_count = self.norm_stft.shape[1]
            self.frames_per_second = sr / hop_length

            if lyric_path and os.path.exists(lyric_path):
                self.lyrics = self._parse_lrc(lyric_path)
            else:
                default_lrc = os.path.splitext(audio_path)[0] + ".lrc"
                if os.path.exists(default_lrc):
                    self.lyrics = self._parse_lrc(default_lrc)
                else:
                    self.lyrics = []
            self.lyric_list.clear()
            for _, text in self.lyrics:
                item = QListWidgetItem(text)
                item.setForeground(QColor(44, 62, 80))
                self.lyric_list.addItem(item)
            if not self.lyrics:
                self.lyric_list.addItem("（无歌词）")
            self.current_lyric_index = -1

            self.song_title_label.setText(os.path.splitext(os.path.basename(audio_path))[0])

            if cover_path and os.path.exists(cover_path):
                self.cover_path = cover_path
            else:
                covers = glob.glob(os.path.splitext(audio_path)[0] + "_cover.*")
                self.cover_path = covers[0] if covers else None
            self._set_cover_background(self.cover_path)

            if self.stream:
                self.stream.stop()
                self.stream.close()
            self.stream = sd.OutputStream(
                samplerate=sr, channels=1, callback=self._audio_callback,
                blocksize=1024, latency='low'
            )
            self.stream.start()

            self.total_time = len(self.audio_data) / sr
            self.progress_slider.setValue(0)
            self.time_label.setText(f"00:00 / {self._format_time(self.total_time)}")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载音频失败: {e}")
            self.pause_btn.setEnabled(False)
            self.norm_stft = None

    def _parse_lrc(self, lrc_path):
        lyrics = []
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)')
        try:
            with open(lrc_path, 'r', encoding='utf-8') as f:
                for line in f:
                    m = pattern.match(line.strip())
                    if m:
                        minute, sec, ms, text = m.groups()
                        total = int(minute) * 60 + int(sec) + int(ms) / 1000.0
                        if text.strip():
                            lyrics.append((total, text.strip()))
        except Exception:
            pass
        return lyrics

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a);;All Files (*.*)"
        )
        if path:
            self.load_audio(path)

    def _audio_callback(self, outdata, frames, time, status):
        with self.lock:
            if self.paused or self.audio_data is None:
                outdata.fill(0)
                return
            start = self.read_index
            end = start + frames
            data_len = len(self.audio_data)
            if start >= data_len:
                outdata.fill(0)
                return
            avail = min(frames, data_len - start)
            if avail < frames:
                outdata[:avail, 0] = self.audio_data[start:start + avail] * self.volume
                outdata[avail:, 0] = 0
                self.read_index = data_len
            else:
                outdata[:, 0] = self.audio_data[start:start + frames] * self.volume
                self.read_index += frames

    def _update_ui(self):
        if self.audio_data is None:
            return
        if self.is_dragging:
            return

        with self.lock:
            idx = self.read_index
        total = len(self.audio_data)

        if total > 0:
            progress = (idx / total) * 100
            if not self.is_dragging:
                self.progress_slider.setValue(int(progress))

        cur_time = idx / self.sample_rate
        self.time_label.setText(f"{self._format_time(cur_time)} / {self._format_time(self.total_time)}")

        self._update_lyric(cur_time)

        if idx < total and self.norm_stft is not None:
            self._update_spectrum(idx)

        if idx >= total and total > 0:
            self._playback_finished()

    def _update_lyric(self, cur_time):
        if not self.lyrics:
            return
        new_idx = -1
        for i, (t, _) in enumerate(self.lyrics):
            if t <= cur_time:
                new_idx = i
            else:
                break
        if new_idx == self.current_lyric_index:
            return

        if self.current_lyric_index != -1:
            old = self.lyric_list.item(self.current_lyric_index)
            if old:
                old.setBackground(QColor(0, 0, 0, 0))
                old.setForeground(QColor(44, 62, 80))
                f = old.font()
                f.setBold(False)
                old.setFont(f)

        if new_idx != -1 and new_idx < self.lyric_list.count():
            new = self.lyric_list.item(new_idx)
            if new:
                new.setBackground(QColor(74, 144, 217, 80))
                new.setForeground(QColor(0, 0, 0))
                f = new.font()
                f.setBold(True)
                new.setFont(f)
                self.lyric_list.scrollToItem(new, QListWidget.PositionAtCenter)

        self.current_lyric_index = new_idx

    def _update_spectrum(self, idx):
        if self.norm_stft is None or self.frame_count == 0:
            return

        frame = int((idx / self.sample_rate) * self.frames_per_second)
        frame = max(0, min(frame, self.frame_count - 1))
        raw = self.norm_stft[:, frame]

        alpha = self.smooth_alpha
        self.smooth_bar_vals = alpha * raw + (1 - alpha) * self.smooth_bar_vals
        smoothed_bar = self.smooth_bar_vals

        ring_idx = np.linspace(0, self.fft_bins - 1, self.ring_bins, dtype=int)
        raw_ring = raw[ring_idx]
        self.smooth_ring_vals = alpha * raw_ring + (1 - alpha) * self.smooth_ring_vals
        smoothed_ring = self.smooth_ring_vals

        cmap = plt.cm.viridis
        norm = Normalize(vmin=0, vmax=1)
        colors = cmap(norm(smoothed_bar))
        for rect, val, color in zip(self.bar_rects, smoothed_bar, colors):
            rect.set_height(val)
            rect.set_color(color)
        self.bar_ax.set_ylim(0, self.y_max)
        self.bar_canvas.draw_idle()

        ring_colors = cmap(norm(smoothed_ring))
        radii = 0.2 + 0.8 * smoothed_ring
        for i, (angle, radius, color, val) in enumerate(
                zip(self.ring_angles, radii, ring_colors, smoothed_ring)):
            self.ring_lines[i].set_data([angle, angle], [0, radius])
            self.ring_lines[i].set_color(color)
            self.ring_dots[i].set_offsets([[angle, radius]])
            self.ring_dots[i].set_sizes([20 + 80 * val])
            self.ring_dots[i].set_color(color)
        self.ring_ax.set_ylim(0, self.y_max)
        self.ring_canvas.draw_idle()

    def _playback_finished(self):
        if self.stream:
            self.stream.stop()
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸ 暂停")
        self.progress_slider.setValue(100)
        self.time_label.setText(f"{self._format_time(self.total_time)} / {self._format_time(self.total_time)}")

    def _toggle_pause(self):
        if self.audio_data is None:
            return
        with self.lock:
            self.paused = not self.paused
        self.pause_btn.setText("▶ 继续" if self.paused else "⏸ 暂停")
        if not self.paused and self.stream and not self.stream.active:
            self.stream.start()

    def _volume_change(self, val):
        self.volume = val / 100.0

    def _progress_press(self):
        if self.audio_data is None:
            return
        self.is_dragging = True
        with self.lock:
            self.paused = True
        self.pause_btn.setText("▶ 继续")

    def _progress_release(self):
        if self.audio_data is None:
            return
        self.is_dragging = False
        with self.lock:
            self.paused = False
        self.pause_btn.setText("⏸ 暂停")
        if self.stream and not self.stream.active:
            self.stream.start()
        self._progress_changed(self.progress_slider.value())

    def _progress_changed(self, val):
        if self.audio_data is None:
            return
        pos = val / 100.0
        new_idx = int(pos * len(self.audio_data))
        with self.lock:
            self.read_index = new_idx
        cur = new_idx / self.sample_rate
        self.time_label.setText(f"{self._format_time(cur)} / {self._format_time(self.total_time)}")

    @staticmethod
    def _format_time(sec):
        return f"{int(sec // 60):02d}:{int(sec % 60):02d}"

    def closeEvent(self, e):
        plt.close(self.bar_fig)
        plt.close(self.ring_fig)
        self.timer.stop()
        try:
            self.signals.update_ui.disconnect()
        except TypeError:
            pass
        if self.stream:
            self.stream.stop()
            self.stream.close()
        super().closeEvent(e)

class UpdateSignals(QObject):
    update_ui = pyqtSignal()

# ==================== 设置对话框 ====================
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(600, 250)
        self.setModal(True)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        source_tab = QWidget()
        source_layout = QVBoxLayout(source_tab)
        group_layout = QHBoxLayout()
        group_layout.setSpacing(20)

        self.source_checkboxes = []

        for group_name, source_names in SOURCE_GROUPS.items():
            group_box = QGroupBox(group_name)
            group_box.setFlat(True)
            grid = QGridLayout()
            grid.setSpacing(5)
            row, col = 0, 0
            for name in source_names:
                cb = QCheckBox(name)
                cb.setChecked("推荐" in name)
                self.source_checkboxes.append(cb)
                grid.addWidget(cb, row, col)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1
            group_box.setLayout(grid)
            group_layout.addWidget(group_box)
        group_layout.addStretch()
        source_layout.addLayout(group_layout)

        form_layout = QFormLayout()
        self.spin_limit = QSpinBox()
        self.spin_limit.setMinimum(1)
        self.spin_limit.setMaximum(50)
        self.spin_limit.setValue(5)
        form_layout.addRow("每源条数:", self.spin_limit)

        self.check_dedup = QCheckBox("去重")
        self.check_dedup.setToolTip("根据歌曲名和歌手去重，保留第一个来源")
        form_layout.addRow(self.check_dedup)

        source_layout.addLayout(form_layout)
        tabs.addTab(source_tab, "搜索源")

        download_tab = QWidget()
        download_layout = QVBoxLayout(download_tab)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setText(DEFAULT_SAVE_DIR)
        path_layout.addWidget(QLabel("保存路径:"))
        path_layout.addWidget(self.path_edit)
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.browse_path)
        path_layout.addWidget(self.btn_browse)
        self.btn_default = QPushButton("默认")
        self.btn_default.clicked.connect(lambda: self.path_edit.setText(DEFAULT_SAVE_DIR))
        path_layout.addWidget(self.btn_default)
        self.btn_desktop = QPushButton("桌面")
        self.btn_desktop.clicked.connect(lambda: self.path_edit.setText(
            os.path.join(os.path.expanduser("~"), "Desktop")
        ))
        path_layout.addWidget(self.btn_desktop)
        download_layout.addLayout(path_layout)

        fmt_layout = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(FILENAME_FORMATS)
        self.format_custom_edit = QLineEdit()
        self.format_custom_edit.setPlaceholderText("例如: {歌手}/{专辑}/{歌曲名}")
        self.format_custom_edit.hide()
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)
        fmt_layout.addWidget(QLabel("文件名格式:"))
        fmt_layout.addWidget(self.format_combo)
        fmt_layout.addWidget(self.format_custom_edit)
        download_layout.addLayout(fmt_layout)

        self.check_lyric = QCheckBox("下载歌词")
        self.check_cover = QCheckBox("下载封面")
        self.check_cover.setChecked(True)
        download_layout.addWidget(self.check_lyric)
        download_layout.addWidget(self.check_cover)

        label = QLabel("Made By cYy")
        label.setAlignment(Qt.AlignRight)
        download_layout.addWidget(label)

        tabs.addTab(download_tab, "下载设置")

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def on_format_changed(self, index):
        if self.format_combo.currentText() == "自定义":
            self.format_custom_edit.show()
        else:
            self.format_custom_edit.hide()

    def load_settings(self):
        if self.parent() and hasattr(self.parent(), 'settings'):
            settings = self.parent().settings
            pass

    def get_settings(self):
        selected_sources = [cb.text() for cb in self.source_checkboxes if cb.isChecked()]
        return {
            'sources': selected_sources,
            'limit': self.spin_limit.value(),
            'dedup': self.check_dedup.isChecked(),
            'save_dir': self.path_edit.text().strip(),
            'filename_format': self.format_combo.currentText(),
            'custom_format': self.format_custom_edit.text().strip(),
            'download_lyric': self.check_lyric.isChecked(),
            'download_cover': self.check_cover.isChecked()
        }

# ==================== 主窗口 ====================
class ClickableSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        try:
            if event.button() != Qt.LeftButton:
                return super().mousePressEvent(event)
            opt_width = self.width()
            if opt_width <= 0:
                return super().mousePressEvent(event)
            x = event.pos().x()
            x = max(0, min(x, opt_width))
            span = self.maximum() - self.minimum()
            if span <= 0:
                val = self.minimum()
            else:
                ratio = x / opt_width
                val = int(self.minimum() + ratio * span)
            self.setValue(val)
            try:
                self.sliderMoved.emit(val)
            except Exception:
                pass
            event.accept()
        except Exception:
            super().mousePressEvent(event)

class MarqueeLabel(QLabel):
    """可滚动的标签，当文本宽度超过可见宽度时自动滚动"""
    def __init__(self, parent=None, interval=150):
        super().__init__(parent)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.setInterval(interval)
        self._full_text = ""
        self._display_text = ""
        self._scroll_enabled = False
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 设置最小高度，避免高度变化
        self.setMinimumHeight(30)
        # 设置样式，避免背景变化
        self.setStyleSheet("background: transparent;")

    def setText(self, text: str):
        self._full_text = text
        self._offset = 0
        self._timer.stop()
        self._update_display()

    def _update_display(self):
        if not self._full_text:
            super().setText("")
            return
        # 获取当前可用宽度（考虑边距）
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self._full_text)
        label_width = self.width() - 10  # 留边距
        if label_width <= 0:
            label_width = self.width()
        if text_width <= label_width:
            # 文本不超宽，直接显示，停止滚动
            super().setText(self._full_text)
            self._timer.stop()
            self._scroll_enabled = False
            return
        # 文本超宽，启用滚动
        self._scroll_enabled = True
        # 截取从 offset 开始的足够显示的部分
        if self._offset >= len(self._full_text):
            self._offset = 0
        # 寻找最接近显示宽度的截断点
        available = label_width
        # 简单方法：从 offset 开始，逐个字符增加直到宽度超过可用宽度
        chars = list(self._full_text)
        # 为了视觉效果，在末尾添加空格填充，或者显示 " ..."
        # 我们采用循环滚动：显示从 offset 开始的一段，末尾补空格，但为了美观，加上 " ..."
        # 更好：显示一段，然后末尾显示 " ..." 但会占用空间，我们直接滚动显示原文本
        # 方法：取从 offset 开始的足够字符，但可能显示不全，但滚动会不断变化
        # 简便：取从 offset 开始的字符串，如果长度超过可用，则截断
        end = self._offset
        while True:
            test_text = self._full_text[self._offset:end+1]
            if fm.horizontalAdvance(test_text) > available:
                break
            end += 1
            if end > len(self._full_text):
                end = len(self._full_text)
                break
        display = self._full_text[self._offset:end]
        # 如果截断后还超，就减少
        while fm.horizontalAdvance(display) > available and len(display) > 1:
            display = display[:-1]
        # 如果显示内容为空，补一个字符
        if not display:
            display = self._full_text[0]
        super().setText(display)
        # 如果还没启动定时器，启动
        if not self._timer.isActive() and self._scroll_enabled:
            self._timer.start()

    def _scroll(self):
        if not self._full_text:
            return
        # 每次移动一个字符
        self._offset += 1
        if self._offset >= len(self._full_text):
            self._offset = 0
        self._update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口大小变化时重新计算
        self._update_display()

    def enterEvent(self, event):
        # 鼠标悬停时暂停滚动（可选）
        if self._timer.isActive():
            self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # 鼠标离开后继续滚动
        if self._scroll_enabled and not self._timer.isActive():
            self._timer.start()
        super().leaveEvent(event)

class MusicdlGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("musicdlGUI")
        self.setWindowTitle('🎵 音乐下载器 cYy edit')
        self.setMinimumSize(1450, 900)
        self.resize(1450, 900)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(self.get_style_sheet())

        self.playlist = []
        self.current_play_index = -1
        self.play_mode = PlayMode.ListRepeat

        self.setup_title_bar()
        self._init_ui()
        self._signals_inited = False
        self._init_signals()
        self._init_state()
        self._init_player()

        self._requests_session = requests.Session()
        self._requests_session.verify = True

        self._resizing = False
        self._resize_start_pos = QPoint()
        self._resize_start_geo = QRect()

        self.settings = {
            'sources': [
                    'QQ音乐(高质量无损,推荐)'
                ],
            'limit': 5,
            'dedup': False,
            'save_dir': DEFAULT_SAVE_DIR,
            'filename_format': '歌手-歌曲名',
            'custom_format': '',
            'download_lyric': True,
            'download_cover': True
        }

    def setup_title_bar(self):
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(50)

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)
        title_layout.setSpacing(8)

        icon_label = QLabel()
        try:
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_dir, 'icon.ico')
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                self.setWindowIcon(icon)
                pixmap = QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_label.setPixmap(pixmap)
                app = QApplication.instance()
                if app:
                    app.setWindowIcon(icon)
            else:
                if getattr(sys, 'frozen', False):
                    alt_path = os.path.join(os.path.dirname(sys.executable), 'icon.ico')
                    if os.path.exists(alt_path):
                        icon = QIcon(alt_path)
                        self.setWindowIcon(icon)
                        app = QApplication.instance()
                        if app:
                            app.setWindowIcon(icon)
        except Exception:
            pass
        icon_label.setFixedSize(24, 24)
        title_layout.addWidget(icon_label)

        title_label = QLabel("⚡️ cY Mic Cli")
        title_label.setStyleSheet("color: #2C3E50; font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索歌曲、歌手...")
        self.search_input.setFixedWidth(250)
        self.search_input.returnPressed.connect(self.on_search_or_stop)
        title_layout.addWidget(self.search_input)

        self.btn_search_title = QPushButton("🔍")
        self.btn_search_title.setObjectName("titleSearchButton")
        self.btn_search_title.setFixedSize(36, 28)
        self.btn_search_title.clicked.connect(self.on_search_or_stop)
        title_layout.addWidget(self.btn_search_title)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("titleSettingsButton")
        self.btn_settings.setFixedSize(36, 28)
        self.btn_settings.clicked.connect(self.open_settings)
        title_layout.addWidget(self.btn_settings)

        self.btn_about = QPushButton("i")
        self.btn_about.setObjectName("titleAboutButton")
        self.btn_about.setFixedSize(36, 28)
        self.btn_about.clicked.connect(self.show_about)
        title_layout.addWidget(self.btn_about)

        title_layout.addStretch()

        self.btn_minimize = QPushButton("—")
        self.btn_minimize.setObjectName("titleMinButton")
        self.btn_minimize.setFixedSize(32, 32)
        self.btn_minimize.clicked.connect(self.showMinimized)
        title_layout.addWidget(self.btn_minimize)

        self.btn_maximize = QPushButton("□")
        self.btn_maximize.setObjectName("titleMaxButton")
        self.btn_maximize.setFixedSize(32, 32)
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        title_layout.addWidget(self.btn_maximize)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("titleCloseButton")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.clicked.connect(self.close)
        title_layout.addWidget(self.btn_close)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 10, 15, 15)
        content_layout.setSpacing(10)

        playlist_layout = QHBoxLayout()
        playlist_layout.addWidget(QLabel("歌单链接:"))
        self.lineedit_playlist = QLineEdit()
        self.lineedit_playlist.setPlaceholderText("粘贴歌单链接，如 https://music.163.com/#/playlist?id=xxx")
        playlist_layout.addWidget(self.lineedit_playlist, 1)
        playlist_layout.addWidget(QLabel("平台:"))
        self.combo_playlist_source = QComboBox()
        self.combo_playlist_source.addItems(list(PLAYLIST_SOURCE_MAP.keys()))
        playlist_layout.addWidget(self.combo_playlist_source)
        self.button_parse_playlist = QPushButton("📋 解析歌单")
        self.button_parse_playlist.setObjectName("parsePlaylistButton")
        playlist_layout.addWidget(self.button_parse_playlist)
        content_layout.addLayout(playlist_layout)

        # ---- 结果表格与播放器左右布局 ----
        splitter = QSplitter(Qt.Horizontal)
        splitter.splitterMoved.connect(self._adjust_column_widths)
        splitter.setHandleWidth(3)  # 可选，调整分隔条宽度

        # 左侧表格
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(['歌手', '歌曲名', '文件大小', '时长', '专辑', '来源'])
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setObjectName('resultTable')
        self.results_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setStretchLastSection(False)
        self.results_table.customContextMenuRequested.connect(self.show_context_menu)
        self.results_table.doubleClicked.connect(self.on_table_double_click)
        splitter.addWidget(self.results_table)

        # ---- 播放器（集成歌词） ----
        play_group = QGroupBox("播放控制")
        play_group.setObjectName("playGroup")
        play_layout = QVBoxLayout(play_group)  # 改为垂直布局，容纳右侧面板

        # 封面与标题水平布局
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(120, 120)
        self.cover_label.setStyleSheet("border: 1px solid #BDC3C7; border-radius: 4px; background-color: #E8EDF2;")
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setText("🎵")
        self.cover_label.mousePressEvent = self.cover_click  # 点击封面打开可视化
        top_layout.addWidget(self.cover_label)

        self.now_playing_label = MarqueeLabel(self)
        self.now_playing_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.now_playing_label.setStyleSheet("font-weight: bold; color: #1E88E5; font-size: 16px;")
        self.now_playing_label.setObjectName("nowPlayingLabel")
        self.now_playing_label.setFixedHeight(30)
        top_layout.addWidget(self.now_playing_label, 1)  # 拉伸填充剩余宽度

        play_layout.addLayout(top_layout)

        # 歌词显示（位于封面和标题下方）
        self.lyric_display = QListWidget()
        self.lyric_display.setSelectionMode(QAbstractItemView.NoSelection)
        self.lyric_display.setWordWrap(True)
        lyric_font = QFont("Microsoft YaHei", 10)
        self.lyric_display.setFont(lyric_font)
        self.lyric_display.setMinimumHeight(80)
        self.lyric_display.setStyleSheet(
            "QListWidget { background: rgba(240, 244, 248, 0.8); border: 1px solid #BDC3C7; border-radius: 4px; }"
            "QListWidget::item { padding: 2px 5px; }"
        )
        play_layout.addWidget(self.lyric_display, 1)  # 歌词占用剩余垂直空间

        # 进度条和时间
        progress_layout = QHBoxLayout()
        self.slider_position = ClickableSlider(Qt.Horizontal, self)
        self.slider_position.setRange(0, 0)
        self.slider_position.setTracking(True)
        self.label_time = QLabel("00:00 / 00:00")
        self.label_time.setMinimumWidth(120)
        self.label_time.setStyleSheet("background-color: transparent; color: #2C3E50;")
        progress_layout.addWidget(self.slider_position, 1)
        progress_layout.addWidget(self.label_time)
        play_layout.addLayout(progress_layout)

        # 控制按钮行 - 第一行：播放控制按钮
        controls_row1 = QHBoxLayout()
        self.btn_prev = QPushButton("⏪")
        self.btn_prev.setObjectName("prevButton")
        self.btn_prev.setFixedWidth(50)
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("playButton")
        self.btn_play.setFixedWidth(60)
        self.btn_next = QPushButton("⏩")
        self.btn_next.setObjectName("nextButton")
        self.btn_next.setFixedWidth(50)
        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setObjectName("stopButton")
        self.btn_stop.setFixedWidth(50)

        controls_row1.addWidget(self.btn_prev)
        controls_row1.addWidget(self.btn_play)
        controls_row1.addWidget(self.btn_next)
        controls_row1.addWidget(self.btn_stop)
        controls_row1.addStretch()  # 使按钮靠左

        play_layout.addLayout(controls_row1)

        # 控制按钮行 - 第二行：可视化、音量、模式
        controls_row2 = QHBoxLayout()
        self.btn_visualize = QPushButton("🎨")
        self.btn_visualize.setObjectName("visualizeButton")
        self.btn_visualize.setFixedWidth(50)
        self.btn_visualize.setToolTip("打开可视化窗口")
        controls_row2.addWidget(self.btn_visualize)
        controls_row2.addStretch()

        controls_row2.addWidget(QLabel("🔊"))
        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(60)
        self.slider_volume.setFixedWidth(80)
        controls_row2.addWidget(self.slider_volume)

        controls_row2.addStretch()
        controls_row2.addWidget(QLabel("模式:"))
        self.combo_playmode = QComboBox()
        self.combo_playmode.addItems(["单曲循环", "单曲暂停", "列表循环", "列表暂停"])
        self.combo_playmode.setCurrentIndex(2)
        self.combo_playmode.currentIndexChanged.connect(self.on_playmode_changed)
        controls_row2.addWidget(self.combo_playmode)

        play_layout.addLayout(controls_row2)
        splitter.addWidget(play_group)
        play_group.setMinimumWidth(280)

        # 设置拉伸因子（表格:播放控制 = 3:1）
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        content_layout.addWidget(splitter, 1)  # 添加到主布局，拉伸因子1

        progress_layout2 = QHBoxLayout()
        progress_layout2.addWidget(QLabel("单曲进度:"))
        self.bar_download = QProgressBar()
        self.bar_download.setObjectName('progressBar')
        progress_layout2.addWidget(self.bar_download)
        progress_layout2.addWidget(QLabel("总进度:"))
        self.bar_overall = QProgressBar()
        self.bar_overall.setObjectName('overallProgressBar')
        progress_layout2.addWidget(self.bar_overall)
        content_layout.addLayout(progress_layout2)

        self.label_stats = QLabel('就绪')
        self.label_stats.setObjectName('statsLabel')
        self.label_stats.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.label_stats)

        self.context_menu = QMenu(self)
        self.action_download = self.context_menu.addAction('⬇️ 下载选中')
        self.action_download.setObjectName('downloadAction')
        self.action_download.triggered.connect(self.download_selected)

        main_layout.addWidget(content_widget)

        self.column_weights = [2.0, 2.0, 1.0, 1.0, 2.0, 1.5]

    def get_style_sheet(self):
        return """
        QWidget {
            font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", "Segoe UI", sans-serif;
            font-size: 12px;
        }
        QWidget#musicdlGUI {
            background-color: #F5F7FA;
            border-radius: 8px;
        }
        #titleBar {
            background-color: #E8F0FE;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            border-bottom: 1px solid #BDC3C7;
        }
        #titleBar QLabel {
            background: transparent;
            font-size: 14px;
        }
        #titleSearchButton, #titleSettingsButton, #titleAboutButton {
            background-color: transparent;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            color: #2C3E50;
        }
        #titleSearchButton:hover, #titleSettingsButton:hover, #titleAboutButton:hover {
            background-color: #D5D8DC;
        }
        #titleMinButton, #titleMaxButton, #titleCloseButton {
            background-color: transparent;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            color: #2C3E50;
        }
        #titleMinButton:hover { background-color: #D5D8DC; }
        #titleMaxButton:hover { background-color: #D5D8DC; }
        #titleCloseButton:hover { background-color: #E74C3C; color: white; }
        #contentWidget {
            background-color: rgba(200, 225, 245, 240);
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #BDC3C7;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QGroupBox#playGroup {
            background-color: #E8F0FE;
            border-color: #4A90D9;
        }
        QLabel { color: #2C3E50; }
        QCheckBox { color: #2C3E50; spacing: 5px; }
        QCheckBox::indicator { width: 16px; height: 16px; }
        QLineEdit, QSpinBox, QComboBox {
            background-color: white;
            border: 1px solid #BDC3C7;
            border-radius: 5px;
            padding: 5px;
            color: #2C3E50;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
            border: 1px solid #4A90D9;
        }
        QPushButton {
            background-color: #E8EDF2;
            color: #2C3E50;
            border: 1px solid #BDC3C7;
            border-radius: 4px;
            padding: 4px 10px;
        }
        QPushButton:hover { background-color: #D5D8DC; }
        QPushButton#playButton {
            background-color: #4A90D9;
            color: white;
            font-weight: bold;
            border: none;
        }
        QPushButton#playButton:hover { background-color: #357ABD; }
        QPushButton#stopButton {
            background-color: #E67E22;
            color: white;
            font-weight: bold;
            border: none;
        }
        QPushButton#stopButton:hover { background-color: #D35400; }
        QPushButton#prevButton, QPushButton#nextButton {
            background-color: #5DADE2;
            color: white;
            font-weight: bold;
            border: none;
            border-radius: 4px;
        }
        QPushButton#prevButton:hover, QPushButton#nextButton:hover {
            background-color: #3498DB;
        }
        QPushButton#visualizeButton {
            background-color: #8E44AD;
            color: white;
            font-weight: bold;
            border: none;
            border-radius: 4px;
        }
        QPushButton#visualizeButton:hover { background-color: #6C3483; }
        QPushButton#parsePlaylistButton {
            background-color: #8E44AD;
            color: white;
            font-weight: bold;
            border: none;
            border-radius: 4px;
        }
        QPushButton#parsePlaylistButton:hover { background-color: #6C3483; }
        QTableWidget#resultTable {
            background-color: white;
            alternate-background-color: #ECF0F1;
            border: 1px solid #BDC3C7;
            border-radius: 5px;
            gridline-color: #D5D8DC;
        }
        QTableWidget::item { padding: 4px; color: #2C3E50; }
        QTableWidget::item:selected { background-color: #4A90D9; color: white; }
        QHeaderView::section {
            background-color: #4A90D9;
            color: white;
            padding: 5px;
            border: none;
        }
        QProgressBar {
            border: 1px solid #BDC3C7;
            border-radius: 5px;
            background-color: white;
            text-align: center;
            color: #2C3E50;
            font-weight: bold;
        }
        QProgressBar::chunk {
            background-color: #4A90D9;
            border-radius: 5px;
        }
        QLabel#statsLabel {
            color: #1E88E5;
            font-weight: bold;
            font-size: 13px;
            background-color: rgba(74, 144, 217, 0.1);
            border-radius: 5px;
            padding: 4px;
        }
        QMenu {
            background-color: white;
            border: 1px solid #BDC3C7;
            border-radius: 5px;
        }
        QMenu::item {
            padding: 6px 20px;
            color: #2C3E50;
        }
        QMenu::item:selected {
            background-color: #4A90D9;
            color: white;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #D5D8DC;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #4A90D9;
            width: 14px;
            height: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        QSlider::sub-page:horizontal {
            background: #4A90D9;
            border-radius: 3px;
        }
        QListWidget {
            background-color: transparent;
            border: none;
            outline: none;
        }
        QListWidget::item {
            padding: 2px 5px;
        }
        QListWidget::item:selected {
            background: transparent;
        }
        """

    def _init_signals(self):
        self.button_parse_playlist.clicked.connect(self.parse_playlist)
        self.btn_play.clicked.connect(self.toggle_playback)
        self.btn_stop.clicked.connect(self.stop_playback)
        self.slider_position.sliderMoved.connect(self.set_position)
        self.slider_volume.valueChanged.connect(self.set_volume)
        self.btn_prev.clicked.connect(self.play_prev)
        self.btn_next.clicked.connect(self.play_next)
        self.btn_visualize.clicked.connect(self.show_visualization)

    def _init_state(self):
        self.search_in_progress = False
        self.is_downloading = False
        self.is_parsing = False
        self._parse_ignore_signals = False
        self.search_thread = None
        self.download_thread = None
        self.parse_thread = None
        self.music_records = {}
        self.music_client = None
        self._source_counts = {}
        self._download_queue = []
        self._download_current_index = 0
        self._total_to_download = 0
        self._downloaded_files = []
        self._adjusting = False
        self._cover_task_id = 0
        self._last_cover_runnable = None
        self.current_lyrics = []
        self.current_lyric_index = -1

        self.drag_pos = QPoint()
        self.dragging = False
        self._vis_download_thread = None

    def _init_player(self):
        self.player = PlayerWrapper()
        self.player.setVolume(self.slider_volume.value())
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.stateChanged.connect(self.update_play_button)
        self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.player.positionChanged.connect(self.update_lyric_display)

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.spin_limit.setValue(self.settings['limit'])
        dlg.check_dedup.setChecked(self.settings['dedup'])
        dlg.path_edit.setText(self.settings['save_dir'])
        dlg.format_combo.setCurrentText(self.settings['filename_format'])
        dlg.format_custom_edit.setText(self.settings['custom_format'])
        dlg.check_lyric.setChecked(self.settings['download_lyric'])
        dlg.check_cover.setChecked(self.settings['download_cover'])
        for cb in dlg.source_checkboxes:
            cb.setChecked(cb.text() in self.settings['sources'])

        if dlg.exec_() == QDialog.Accepted:
            new_settings = dlg.get_settings()
            self.settings.update(new_settings)
            self.label_stats.setText("设置已更新")

    def show_about(self):
        QMessageBox.about(self, "关于", 
            "🎵 cYy Music Client\n"
            "基于 PyQt5 + musicdl\n"
            "版本 4.1.0\n"
            "本程序遵循 GNU 3.0 开源协议\n"
            "© 2026 cYy"
        )

    def cover_click(self, event):
        self.show_visualization()

    def on_search_or_stop(self):
        if self.is_parsing:
            self._show_warning('提示', '正在解析歌单，请稍后再试')
            return
        if not self.search_in_progress:
            self.start_search()
        else:
            self.stop_search()

    def start_search(self):
        selected_display = self.settings.get('sources', [])
        if not selected_display:
            QMessageBox.warning(self, '警告', '请先在设置中选择搜索源')
            return
        selected_sources = []
        for display in selected_display:
            internal = SOURCE_INTERNAL.get(display)
            if internal:
                selected_sources.append(internal)
        if not selected_sources:
            QMessageBox.warning(self, '警告', '未找到有效的搜索源')
            return

        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, '警告', '请输入关键词')
            return

        limit = self.settings.get('limit', 5)
        dedup = self.settings.get('dedup', False)

        self.clear_results()

        init_cfg = {}
        for src in selected_sources:
            init_cfg[src] = {'search_size_per_source': limit}

        try:
            self.music_client = musicdl.MusicClient(
                music_sources=selected_sources,
                init_music_clients_cfg=init_cfg
            )
        except Exception as e:
            QMessageBox.critical(self, '初始化失败', f'无法创建音乐客户端：{str(e)}')
            return

        self.label_stats.setText(f'⏳ 搜索中 (0/{len(selected_sources)}) ...')
        self._source_counts = {src: -1 for src in selected_sources}

        self._set_ui_enabled(False)
        self.btn_search_title.setText('⏹')
        self.btn_search_title.setToolTip('停止搜索')
        self.search_in_progress = True

        self.search_thread = SearchThread(
            self.music_client,
            selected_sources,
            keyword,
            limit,
            threadings_per_source=5,
        )
        self.search_thread.source_started.connect(self.on_source_started)
        self.search_thread.source_finished.connect(self.on_source_finished)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.error.connect(self.on_search_error)
        self.search_thread.start()

    def stop_search(self):
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.stop()
            self.btn_search_title.setEnabled(False)
            self.btn_search_title.setText('⏹')
            self.label_stats.setText('⏹ 正在停止搜索...')
            try:
                self.search_thread.finished.disconnect(self.on_search_finished)
            except TypeError:
                pass
            self._restore_search_ui()
        else:
            self.finish_search()

    def _restore_search_ui(self):
        self.search_in_progress = False
        self._set_ui_enabled(True)
        self.btn_search_title.setEnabled(True)
        self.btn_search_title.setText('🔍')
        self.btn_search_title.setToolTip('搜索')
        if self.label_stats.text().startswith('⏹ 正在停止搜索'):
            self.label_stats.setText('已停止搜索')
        self.search_thread = None

    def _set_ui_enabled(self, enabled: bool):
        self.search_input.setEnabled(enabled)
        self.btn_search_title.setEnabled(True)
        self.button_parse_playlist.setEnabled(enabled)
        self.lineedit_playlist.setEnabled(enabled)
        self.combo_playlist_source.setEnabled(enabled)
        self.btn_settings.setEnabled(enabled)
        self.btn_about.setEnabled(enabled)
        self.action_download.setEnabled(enabled and not self.is_downloading)

    def finish_search(self):
        self.search_in_progress = False
        self.btn_search_title.setEnabled(True)
        self.btn_search_title.setText('🔍')
        self.btn_search_title.setToolTip('搜索')
        self._set_ui_enabled(True)
        if self.results_table.rowCount() == 0:
            if not self.label_stats.text().startswith('❌'):
                self.label_stats.setText('❌ 未找到任何结果')
        if self.search_thread:
            try:
                self.search_thread.deleteLater()
            except Exception:
                pass
            self.search_thread = None

    def on_source_started(self, source_internal: str):
        display = self._internal_to_display(source_internal)
        self.label_stats.setText(f'⏳ 正在搜索 {display} ...')

    def on_source_finished(self, source_internal: str, results: List):
        display = self._internal_to_display(source_internal)
        count = len(results)
        self._source_counts[source_internal] = count

        current_row = self.results_table.rowCount()
        dedup = self.settings.get('dedup', False)

        if dedup:
            existing = set()
            for row in range(self.results_table.rowCount()):
                singer = self.results_table.item(row, 0).text() if self.results_table.item(row, 0) else ''
                song = self.results_table.item(row, 1).text() if self.results_table.item(row, 1) else ''
                existing.add((singer, song))
            new_items = []
            for idx, item in enumerate(results):
                singer = item.get('singers', '')
                song = item.get('song_name', '')
                if (singer, song) not in existing:
                    existing.add((singer, song))
                    new_items.append((str(current_row + idx), item))
        else:
            new_items = [(str(current_row + idx), item) for idx, item in enumerate(results)]

        if not new_items:
            total = self.results_table.rowCount()
            done = sum(1 for v in self._source_counts.values() if v >= 0)
            total_sources = len(self._source_counts)
            self.label_stats.setText(
                f'⏳ 已搜索 {done}/{total_sources} 个源，共 {total} 条结果（新增0条）'
            )
            return

        try:
            self.results_table.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            self.results_table.setRowCount(current_row + len(new_items))
            for idx, (row_key, item) in enumerate(new_items):
                row = current_row + idx
                self.music_records[row_key] = item
                col_data = [
                    item.get('singers', ''),
                    item.get('song_name', ''),
                    item.get('file_size', ''),
                    item.get('duration', ''),
                    item.get('album', ''),
                    display
                ]
                for col, text in enumerate(col_data):
                    table_item = QTableWidgetItem(str(text))
                    table_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                    self.results_table.setItem(row, col, table_item)
        finally:
            try:
                self.results_table.setUpdatesEnabled(True)
            except Exception:
                pass

        total = self.results_table.rowCount()
        done = sum(1 for v in self._source_counts.values() if v >= 0)
        total_sources = len(self._source_counts)
        self.label_stats.setText(
            f'⏳ 已搜索 {done}/{total_sources} 个源，共 {total} 条结果'
        )

    def on_search_finished(self):
        if self.search_in_progress:
            self.finish_search()
            total = self.results_table.rowCount()
            if total > 0:
                self.label_stats.setText(f'✅ 搜索完成，共 {total} 条结果')
            else:
                self.label_stats.setText('❌ 未搜索到任何结果')
            QTimer.singleShot(100, self._adjust_column_widths)

    def on_search_error(self, error_msg: str):
        QMessageBox.warning(self, '搜索警告', error_msg)

    def _internal_to_display(self, internal: str) -> str:
        for k, v in SOURCE_INTERNAL.items():
            if v == internal:
                return k
        return internal

    def parse_playlist(self):
        if self.search_in_progress:
            self._show_warning('提示', '正在搜索中，请稍后再试')
            return
        if self.is_downloading:
            self._show_warning('提示', '正在下载中，请稍后再试')
            return
        if self.is_parsing:
            self.stop_parse()
            return

        playlist_url = self.lineedit_playlist.text().strip()
        if not playlist_url:
            QMessageBox.warning(self, '警告', '请先输入歌单链接')
            return

        source_display = self.combo_playlist_source.currentText()
        source_internal = PLAYLIST_SOURCE_MAP.get(source_display)
        if not source_internal:
            QMessageBox.warning(self, '警告', '请选择有效的歌单平台')
            return

        self._parse_ignore_signals = False
        self._set_ui_enabled(False)
        self.button_parse_playlist.setEnabled(True)
        self.button_parse_playlist.setText('⏹ 停止')
        self.is_parsing = True
        self.label_stats.setText('⏳ 正在解析歌单...')

        self.parse_thread = PlaylistParseThread(playlist_url, source_internal, source_display)
        self.parse_thread.parse_started.connect(self._on_parse_started)
        self.parse_thread.parse_finished.connect(self._on_parse_finished)
        self.parse_thread.parse_error.connect(self._on_parse_error)
        self.parse_thread.finished.connect(self._on_parse_thread_finished)
        self.parse_thread.start()

    def stop_parse(self):
        if self.parse_thread and self.parse_thread.isRunning():
            self.parse_thread.stop()
            self._parse_ignore_signals = True
            self._restore_parse_ui()
            try:
                self.parse_thread.finished.disconnect(self._on_parse_thread_finished)
            except TypeError:
                pass
        else:
            self._restore_parse_ui()

    def _restore_parse_ui(self):
        self.is_parsing = False
        self._set_ui_enabled(True)
        self.button_parse_playlist.setEnabled(True)
        self.button_parse_playlist.setText('📋 解析歌单')
        if self.label_stats.text().startswith('⏹ 正在停止解析'):
            self.label_stats.setText('已停止解析')

    def _on_parse_started(self):
        if self._parse_ignore_signals:
            return
        self.label_stats.setText('⏳ 正在解析歌单...')

    def _on_parse_finished(self, song_infos, source_display):
        if self._parse_ignore_signals:
            return
        current_row = self.results_table.rowCount()
        self.results_table.setRowCount(current_row + len(song_infos))

        for idx, song_info in enumerate(song_infos):
            row = current_row + idx
            row_key = str(row)
            self.music_records[row_key] = song_info

            col_data = [
                song_info.get('singers', ''),
                song_info.get('song_name', ''),
                song_info.get('file_size', ''),
                song_info.get('duration', ''),
                song_info.get('album', ''),
                source_display
            ]
            for col, text in enumerate(col_data):
                table_item = QTableWidgetItem(str(text))
                table_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                self.results_table.setItem(row, col, table_item)

        self.label_stats.setText(f'✅ 歌单解析成功，共 {len(song_infos)} 首歌曲')
        QTimer.singleShot(100, self._adjust_column_widths)

    def _on_parse_error(self, error_msg):
        if self._parse_ignore_signals:
            return
        logger.error(f"歌单解析错误: {error_msg}")
        QMessageBox.critical(self, '解析失败', f'歌单解析出错：{error_msg}\n\n请确认链接格式正确且平台支持。')
        self.label_stats.setText('❌ 歌单解析失败')

    def _on_parse_thread_finished(self):
        if not self._parse_ignore_signals:
            self._restore_parse_ui()
        else:
            self._parse_ignore_signals = False
        self.parse_thread = None

    def clear_results(self):
        self.results_table.setRowCount(0)
        self.music_records.clear()
        self.label_stats.setText('已清空')
        self._source_counts.clear()
        self.playlist = []
        self.current_play_index = -1
        self.stop_playback()

    def show_context_menu(self, pos):
        if not self.is_downloading and self.results_table.rowCount() > 0:
            self.context_menu.exec_(self.results_table.mapToGlobal(pos))

    def download_selected(self):
        if self.is_downloading:
            QMessageBox.information(self, '提示', '正在下载中，请稍候...')
            return

        selected_rows = set()
        for item in self.results_table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            QMessageBox.warning(self, '警告', '请先选择至少一首歌曲')
            return

        songs_to_download = []
        for row in sorted(selected_rows):
            row_key = str(row)
            info = self.music_records.get(row_key)
            if info and info.get('download_url'):
                songs_to_download.append(info)
            else:
                QMessageBox.warning(self, '警告', f'第 {row+1} 首歌曲无有效下载链接，已跳过')

        if not songs_to_download:
            return

        save_dir = self.settings['save_dir']
        if not save_dir:
            QMessageBox.warning(self, '警告', '请选择有效的保存路径')
            return
        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir)
            except Exception as e:
                QMessageBox.critical(self, '错误', f'无法创建目录：{str(e)}')
                return

        fmt = self._get_filename_template()
        dl_lyric = self.settings['download_lyric']
        dl_cover = self.settings['download_cover']

        self.is_downloading = True
        self._set_ui_enabled(False)
        self.results_table.setEnabled(False)
        self.action_download.setEnabled(False)

        self._download_queue = songs_to_download.copy()
        self._download_current_index = 0
        self._total_to_download = len(songs_to_download)
        self._downloaded_files.clear()

        self.bar_overall.setMaximum(self._total_to_download)
        self.bar_overall.setValue(0)
        self.bar_download.setValue(0)

        self._start_next_download()

    def cancel_all_downloads(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            try:
                self.download_thread.progress.disconnect()
                self.download_thread.finished.disconnect()
                self.download_thread.error.disconnect()
            except TypeError:
                pass

        self._download_queue.clear()
        files_to_delete = self._downloaded_files.copy()

        def do_cleanup():
            for f in files_to_delete:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except Exception as e:
                    logger.error(f"删除文件失败 {f}: {e}")
            for f in files_to_delete:
                base = os.path.splitext(f)[0]
                try:
                    for pattern in [base + '.lrc'] + glob.glob(base + '_cover.*'):
                        try:
                            if os.path.exists(pattern):
                                os.remove(pattern)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"清理关联文件时出错: {e}")
            self._downloaded_files.clear()
            self._on_all_downloads_finished(cancelled=True)

        QTimer.singleShot(500, do_cleanup)

    def _get_request_kwargs_for_source(self, source: str) -> Dict:
        kwargs = {
            'headers': {},
            'cookies': {},
            'proxies': {},
            'timeout': 30,
            'verify': True
        }
        if self.music_client:
            client = self.music_client.music_clients.get(source)
            if client:
                for attr in ('default_download_headers', 'default_headers', 'default_search_headers', 'default_parse_headers'):
                    if hasattr(client, attr):
                        kwargs['headers'].update(getattr(client, attr) or {})
                for attr in ('default_download_cookies', 'default_cookies', 'default_search_cookies', 'default_parse_cookies'):
                    if hasattr(client, attr):
                        kwargs['cookies'].update(getattr(client, attr) or {})
        return kwargs

    def _start_next_download(self):
        if self._download_current_index >= len(self._download_queue):
            self._on_all_downloads_finished()
            return

        song_info = self._download_queue[self._download_current_index]
        self.bar_download.setValue(0)
        self.label_stats.setText(
            f'⏳ 下载中 ({self._download_current_index+1}/{self._total_to_download}) ...'
        )

        self.download_thread = DownloadThread(
            song_info,
            self._get_request_kwargs_for_source,
            self.settings['save_dir'],
            self._get_filename_template(),
            self.settings['download_lyric'],
            self.settings['download_cover']
        )
        self.download_thread.progress.connect(self.bar_download.setValue)
        self.download_thread.finished.connect(self._on_single_download_finished)
        self.download_thread.error.connect(self._on_single_download_error)
        self.download_thread.start()

    def _on_single_download_finished(self, song_name, singers, file_path):
        self._download_current_index += 1
        self.bar_overall.setValue(self._download_current_index)
        self.label_stats.setText(
            f'✅ 已完成 {self._download_current_index}/{self._total_to_download}: {song_name} - {singers}'
        )
        logger.info(f"下载成功: {song_name} - {singers} -> {file_path}")

        self._downloaded_files.append(file_path)
        base = os.path.splitext(file_path)[0]
        for pattern in [base + '.lrc'] + glob.glob(base + '_cover.*'):
            if os.path.exists(pattern):
                self._downloaded_files.append(pattern)

        self._start_next_download()

    def _on_single_download_error(self, error_msg):
        QMessageBox.critical(self, '下载错误', f'下载失败：{error_msg}')
        self._download_current_index += 1
        self.bar_overall.setValue(self._download_current_index)
        self._start_next_download()

    def _on_all_downloads_finished(self, cancelled=False):
        self.is_downloading = False
        self._set_ui_enabled(True)
        self.results_table.setEnabled(True)
        self.action_download.setEnabled(True)
        if not cancelled:
            self.bar_download.setValue(0)
            self.bar_overall.setValue(self._total_to_download)
            self.label_stats.setText(f'✅ 所有下载任务已完成 ({self._total_to_download} 首)')
            QMessageBox.information(self, '下载完成',
                                    f'全部 {self._total_to_download} 首歌曲下载完毕。')
        else:
            self.bar_download.setValue(0)
            self.bar_overall.setValue(0)
            self.label_stats.setText('❌ 下载已取消')
            QMessageBox.information(self, '取消', '所有下载任务已取消。')
        if self.download_thread:
            try:
                self.download_thread.deleteLater()
            except Exception:
                pass
            self.download_thread = None
        self._download_queue = []
        self._downloaded_files.clear()

    def _adjust_column_widths(self):
        if self._adjusting:
            return
        self._adjusting = True
        table = self.results_table
        total_width = table.viewport().width()
        if total_width <= 0:
            self._adjusting = False
            return
        weights = self.column_weights
        total_weight = sum(weights)
        header = table.horizontalHeader()
        for col, weight in enumerate(weights):
            width = int(total_width * weight / total_weight)
            header.resizeSection(col, max(width, 30))
        self._adjusting = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_column_widths()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._adjust_column_widths)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            if pos.x() >= self.width() - 15 and pos.y() >= self.height() - 15:
                self._resizing = True
                self._resize_start_pos = event.globalPos()
                self._resize_start_geo = self.geometry()
                event.accept()
                return
            if hasattr(self, 'title_bar') and self.title_bar.geometry().contains(pos):
                self.drag_pos = event.globalPos()
                self.dragging = True
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.globalPos() - self._resize_start_pos
            new_width = max(self.minimumWidth(), self._resize_start_geo.width() + delta.x())
            new_height = max(self.minimumHeight(), self._resize_start_geo.height() + delta.y())
            self.resize(new_width, new_height)
            event.accept()
            return
        if hasattr(self, 'dragging') and self.dragging:
            delta = event.globalPos() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        if hasattr(self, 'dragging') and self.dragging:
            self.dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if hasattr(self, 'title_bar') and self.title_bar.geometry().contains(event.pos()):
            self.toggle_maximize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_maximize.setText("□")
        else:
            self.showMaximized()
            self.btn_maximize.setText("❐")

    def closeEvent(self, event):
        if hasattr(self, '_vis_download_thread') and self._vis_download_thread is not None:
            if self._vis_download_thread.isRunning():
                self._vis_download_thread.stop()
                self._vis_download_thread.wait()
            self._vis_download_thread = None
        if self.search_thread and self.search_thread.isRunning():
            try:
                self.search_thread.stop()
            except Exception:
                pass
        if self.download_thread and self.download_thread.isRunning():
            try:
                self.download_thread.stop()
            except Exception:
                pass
        if self.parse_thread and self.parse_thread.isRunning():
            try:
                self.parse_thread.stop()
            except Exception:
                pass
        if self.player.state() != PlayerState.StoppedState:
            self.player.stop()
        self._cover_task_id += 1
        try:
            if hasattr(self, '_requests_session') and self._requests_session:
                self._requests_session.close()
        except Exception:
            pass
        event.accept()

    def _show_warning(self, title: str, text: str):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.NoIcon)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    def show_visualization(self):
        if self.current_play_index < 0 or not self.playlist:
            QMessageBox.information(self, "提示", "请先播放一首歌曲")
            return

        song_info = self.playlist[self.current_play_index]
        base_name = self._get_base_name_for_song(song_info, "{歌手}-{歌曲名}")
        ext = song_info.get('ext', 'mp3')
        save_dir = self.settings['save_dir']
        pattern = os.path.join(save_dir, f"{base_name}*{ext}")
        matches = glob.glob(pattern)
        audio_file = None
        for f in matches:
            if '_cover' not in f and '.lrc' not in f:
                audio_file = f
                break
        if not audio_file and matches:
            audio_file = matches[0]

        if audio_file and os.path.exists(audio_file):
            self._open_visualization(audio_file, song_info)
        else:
            reply = QMessageBox.question(self, "文件未下载",
                                         "当前歌曲尚未下载到本地，是否立即下载？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._download_and_visualize(song_info)

    def _open_visualization(self, audio_file, song_info):
        if hasattr(self, 'vis_window') and self.vis_window is not None:
            try:
                self.vis_window.close()
            except RuntimeError:
                pass
            self.vis_window = None

        if self.player.state() == PlayerState.PlayingState:
            self.player.pause()

        base, _ = os.path.splitext(audio_file)
        lyric_file = base + '.lrc'
        cover_file = None
        cover_pattern = base + '_cover.*'
        covers = glob.glob(cover_pattern)
        if covers:
            cover_file = covers[0]

        self.vis_window = AudioVisualizer(
            audio_file,
            lyric_file if os.path.exists(lyric_file) else None,
            cover_file if cover_file and os.path.exists(cover_file) else None,
            parent=self
        )
        self.vis_window.destroyed.connect(self._on_vis_window_destroyed)
        self.vis_window.show()

    def _on_vis_window_destroyed(self):
        self.vis_window = None

    def _download_and_visualize(self, song_info):
        save_dir = self.settings['save_dir']
        fmt = "{歌手}-{歌曲名}"
        dl_lyric = True
        dl_cover = True

        if hasattr(self, '_vis_download_thread') and self._vis_download_thread is not None:
            if self._vis_download_thread.isRunning():
                self._vis_download_thread.stop()
                self._vis_download_thread.wait()
            self._vis_download_thread = None

        progress = QProgressDialog("正在下载歌曲...", "取消", 0, 100, self)
        progress.setWindowTitle("下载进度")
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        self._vis_download_thread = DownloadThread(
            song_info,
            self._get_request_kwargs_for_source,
            save_dir,
            fmt,
            dl_lyric,
            dl_cover
        )
        self._vis_download_thread.progress.connect(progress.setValue)
        self._vis_download_thread.finished.connect(
            lambda name, singer, path: self._on_vis_download_finished(name, singer, path, progress)
        )
        self._vis_download_thread.error.connect(
            lambda err: self._on_vis_download_error(err, progress)
        )
        progress.canceled.connect(self._vis_download_thread.stop)

        self._vis_download_thread.start()
        self.label_stats.setText("⏳ 正在下载当前歌曲以用于可视化...")
        self.btn_visualize.setEnabled(False)

    def _on_vis_download_finished(self, song_name, singers, file_path, progress):
        progress.setValue(100)
        progress.close()
        self.btn_visualize.setEnabled(True)
        self.label_stats.setText(f"下载完成：{song_name} - {singers}")
        song_info = self.playlist[self.current_play_index] if self.current_play_index >= 0 else None
        if song_info:
            self._open_visualization(file_path, song_info)
        else:
            QMessageBox.warning(self, "错误", "无法获取歌曲信息")
        self._vis_download_thread = None

    def _on_vis_download_error(self, error_msg, progress):
        progress.close()
        self.btn_visualize.setEnabled(True)
        QMessageBox.critical(self, "下载失败", f"下载可视化所需文件失败：{error_msg}")
        self._vis_download_thread = None

    def _on_cover_loaded(self, payload):
        try:
            if isinstance(payload, tuple) and len(payload) == 2:
                img_data, task_id = payload
                if task_id != self._cover_task_id:
                    logger.debug("收到过期的封面任务结果，忽略")
                    return
            else:
                img_data = payload
            if not img_data:
                self.cover_label.setText("🎵")
                self.cover_label.setPixmap(QPixmap())
                return
            pixmap = QPixmap()
            if pixmap.loadFromData(img_data):
                scaled = pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.cover_label.setPixmap(scaled)
            else:
                self.cover_label.setText("🎵")
                self.cover_label.setPixmap(QPixmap())
        except Exception as e:
            logger.error(f"加载封面失败: {e}", exc_info=True)
            self.cover_label.setText("🎵")
            self.cover_label.setPixmap(QPixmap())

    def _fetch_cover_async(self, url: str, request_kwargs: Dict):
        self._cover_task_id += 1
        task_id = self._cover_task_id
        self._last_cover_runnable = CoverRunnable(url, request_kwargs, task_id, session=self._requests_session)
        self._last_cover_runnable.signals.finished.connect(self._on_cover_loaded)
        QThreadPool.globalInstance().start(self._last_cover_runnable)

    def toggle_playback(self):
        if not self.playlist and self.player.state() == PlayerState.StoppedState:
            QMessageBox.information(self, "提示", "播放列表为空，请先选择歌曲播放。")
            return

        state = self.player.state()
        if state == PlayerState.PlayingState:
            self.player.pause()
        elif state == PlayerState.PausedState:
            self.player.play(volume=self.slider_volume.value())
        else:
            if not self.playlist:
                return
            self.player.setPosition(0)
            self.player.play(volume=self.slider_volume.value())

    def stop_playback(self):
        self.player.stop()
        self.player.setPosition(0)
        self.slider_position.setValue(0)
        self.label_time.setText("00:00 / 00:00")
        self.now_playing_label.setText("未播放")
        self.clear_lyric_display()
        self.cover_label.setText("🎵")
        self.cover_label.setPixmap(QPixmap())
        self._cover_task_id += 1
        self._last_cover_runnable = None
        self.playlist.clear()
        self.current_play_index = -1

    def set_position(self, pos):
        self.player.setPosition(pos)

    def set_volume(self, vol):
        self.player.setVolume(vol)

    def update_position(self, pos):
        self.slider_position.setValue(pos)
        total = self.player.duration()
        if total > 0:
            self.label_time.setText(f"{self._format_time(pos)} / {self._format_time(total)}")
        else:
            self.label_time.setText(f"{self._format_time(pos)} / 00:00")

    def update_duration(self, duration):
        self.slider_position.setRange(0, duration)

    def update_play_button(self, state: PlayerState):
        if state == PlayerState.PlayingState:
            self.btn_play.setText("⏸ 暂停")
        else:
            self.btn_play.setText("▶ 播放")

    def handle_media_status(self, status: PlayerMediaStatus):
        if status == PlayerMediaStatus.InvalidMedia:
            QMessageBox.warning(
                self, "播放失败",
                "无法播放该歌曲，可能原因：\n"
                "• 格式不被系统解码器支持（如 FLAC）\n"
                "• 链接需要特定的 HTTP 请求头（如 Referer）\n\n"
                "建议使用「下载」功能保存到本地后播放。"
            )
            self.now_playing_label.setText("播放失败")
            self.player.reset()
        elif status == PlayerMediaStatus.EndOfMedia:
            self._on_playback_ended()

    def _format_time(self, ms):
        s = ms // 1000
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def on_playmode_changed(self, index):
        self.play_mode = PlayMode(index)

    def _on_playback_ended(self):
        if not self.playlist or self.current_play_index < 0 or self.current_play_index >= len(self.playlist):
            return
        mode = self.play_mode
        if mode == PlayMode.SingleRepeat:
            self.play_current()
        elif mode == PlayMode.SingleStop:
            self.stop_playback()
            self.now_playing_label.setText("播放结束")
        elif mode == PlayMode.ListRepeat:
            next_idx = self.current_play_index + 1
            if next_idx >= len(self.playlist):
                next_idx = 0
            self.current_play_index = next_idx
            self.play_current()
        elif mode == PlayMode.ListStop:
            next_idx = self.current_play_index + 1
            if next_idx >= len(self.playlist):
                self.stop_playback()
                self.now_playing_label.setText("列表播放结束")
            else:
                self.current_play_index = next_idx
                self.play_current()

    def play_song_at_row(self, row):
        playlist = []
        for r in range(self.results_table.rowCount()):
            row_key = str(r)
            info = self.music_records.get(row_key)
            if info:
                playlist.append(info)
        if not playlist:
            return
        self.playlist = playlist
        if row < 0 or row >= len(playlist):
            row = 0
        self.current_play_index = row
        self.play_current()

    def play_current(self):
        if not self.playlist or self.current_play_index < 0 or self.current_play_index >= len(self.playlist):
            return
        song_info = self.playlist[self.current_play_index]
        url = song_info.get('download_url')
        if not url:
            QMessageBox.warning(self, "无法播放", "该歌曲没有可用的播放链接。")
            return

        self.player.stop()
        source = song_info.get('source', '')
        req_kwargs = self._get_request_kwargs_for_source(source)
        headers = req_kwargs.get('headers') or {}
        self.player.setMedia(url, headers=headers)

        singer = song_info.get('singers', '')
        name = song_info.get('song_name', '')
        self.now_playing_label.setText(f"🎵 {singer} - {name}")

        lyric_text = song_info.get('lyric') or song_info.get('lyrics', '')
        if lyric_text:
            self.current_lyrics = self.parse_lrc(lyric_text)
        else:
            self.current_lyrics = []
        self.current_lyric_index = -1
        self.update_lyric_display(0)

        self.player.play(volume=self.slider_volume.value())

        cover_url = get_cover_url(song_info)
        if cover_url:
            req_kwargs = self._get_request_kwargs_for_source(source)
            QTimer.singleShot(300, lambda: self._fetch_cover_async(cover_url, req_kwargs))
        else:
            self.cover_label.setText("🎵")
            self.cover_label.setPixmap(QPixmap())

    def play_prev(self):
        if not self.playlist:
            return
        if self.current_play_index <= 0:
            self.current_play_index = len(self.playlist) - 1
        else:
            self.current_play_index -= 1
        self.play_current()

    def play_next(self):
        if not self.playlist:
            return
        if self.current_play_index >= len(self.playlist) - 1:
            self.current_play_index = 0
        else:
            self.current_play_index += 1
        self.play_current()

    def on_table_double_click(self, index):
        row = index.row()
        self.play_song_at_row(row)

    def parse_lrc(self, text: str) -> List[Tuple[int, str]]:
        lyrics = []
        pattern = r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)'
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(pattern, line)
            if match:
                min_val = int(match.group(1))
                sec_val = int(match.group(2))
                ms_str = match.group(3)
                ms = int(ms_str) * 10 if len(ms_str) == 2 else int(ms_str)
                time_ms = min_val * 60000 + sec_val * 1000 + ms
                content = match.group(4).strip()
                lyrics.append((time_ms, content))
        lyrics.sort(key=lambda x: x[0])
        return lyrics

    def update_lyric_display(self, pos_ms: int):
        if not self.current_lyrics:
            if self.lyric_display.count() == 0 or self.lyric_display.item(0).text() != "暂无歌词":
                self.lyric_display.clear()
                self.lyric_display.addItem("暂无歌词")
                self.current_lyric_index = -1
            return

        selected_index = -1
        for i, (t, _) in enumerate(self.current_lyrics):
            if t <= pos_ms:
                selected_index = i
            else:
                break

        if selected_index == self.current_lyric_index:
            return

        self.current_lyric_index = selected_index
        self.lyric_display.clear()
        for i, (_, text) in enumerate(self.current_lyrics):
            item = QListWidgetItem(text)
            if i == selected_index:
                item.setBackground(QColor(0,130,255))
                item.setForeground(QColor(0,240,240))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.lyric_display.addItem(item)

        if selected_index >= 0:
            self.lyric_display.scrollToItem(
                self.lyric_display.item(selected_index),
                QAbstractItemView.PositionAtCenter
            )

    def clear_lyric_display(self):
        self.current_lyrics = []
        self.current_lyric_index = -1
        self.lyric_display.clear()
        self.lyric_display.addItem("停止播放")

    def _set_save_path(self, path: str):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as e:
                QMessageBox.warning(self, '错误', f'无法创建目录：{e}')
                return
        self.settings['save_dir'] = path

    def _set_path_from_dialog(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.settings['save_dir'])
        if path:
            self._set_save_path(path)

    def open_download_folder(self):
        folder = self.settings['save_dir']
        if not folder:
            QMessageBox.warning(self, '警告', '保存路径为空')
            return
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
            except Exception as e:
                QMessageBox.critical(self, '错误', f'无法创建目录：{e}')
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _get_filename_template(self) -> str:
        fmt = self.settings['filename_format']
        if fmt == '自定义':
            template = self.settings.get('custom_format', '').strip()
            if not template:
                template = '{歌手}-{歌曲名}'
            return template
        return fmt

    def _get_base_name_for_song(self, song_info: Dict, fmt: str = None) -> str:
        if fmt is None:
            fmt = self._get_filename_template()
        song_name = song_info.get('song_name', '')
        singers = song_info.get('singers', '')
        if fmt == "歌曲名":
            base = song_name
        elif fmt == "歌手-歌曲名":
            base = f"{singers}-{song_name}"
        elif fmt == "歌曲名-歌手":
            base = f"{song_name}-{singers}"
        else:
            base = fmt
            base = base.replace("{歌手}", singers)
            base = base.replace("{歌曲名}", song_name)
            base = base.replace("{专辑}", song_info.get('album', ''))
            base = base.replace("{时长}", song_info.get('duration', ''))
        return sanitize_filepath(base)

if __name__ == '__main__':
    if sys.platform == 'darwin':
        try:
            test_file = os.path.join(os.getcwd(), '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except OSError:
            os.chdir(os.path.expanduser("~"))
    
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei", 10)
    if sys.platform == 'darwin':
        font.setFamily("PingFang SC")
    app.setFont(font)
    gui = MusicdlGUI()
    gui.show()
    sys.exit(app.exec_())
