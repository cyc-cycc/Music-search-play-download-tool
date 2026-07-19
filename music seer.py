import os
import re
import sys
import threading
import glob
import numpy as np
import sounddevice as sd
import librosa
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QFrame, QSplitter,
    QMessageBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt5.QtGui import QFont, QPalette, QColor, QPixmap
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.colors import Normalize
import matplotlib.pyplot as plt

# 解决中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


def parse_lrc(lrc_path):
    """解析歌词文件，返回 [(时间秒, 文本), ...]"""
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


class UpdateSignals(QObject):
    """用于跨线程更新UI的信号"""
    update_ui = pyqtSignal()


class AudioVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("音频可视化播放器")
        self.setGeometry(100, 100, 800, 700)
        self.setMinimumSize(700, 700)

        # 状态变量
        self.audio_data = None          # 单声道float32
        self.sample_rate = None
        self.read_index = 0
        self.lock = threading.Lock()
        self.paused = False
        self.volume = 1.0
        self.stream = None
        self.lyrics = []                # [(time, text), ...]
        self.current_lyric_index = -1
        self.total_time = 0
        self.is_dragging = False

        # 频谱参数
        self.fft_bins = 60
        self.ring_bins = 48
        self.y_max = 1.1
        self.smooth_alpha = 0.4
        self.smooth_bar_vals = None
        self.smooth_ring_vals = None

        # 预计算 Mel 频谱
        self.norm_stft = None
        self.frame_count = 0
        self.frames_per_second = 0.0

        # 封面路径
        self.cover_path = None

        # 窗口拖动
        self.drag_pos = QPoint()
        self.dragging = False

        # 信号与定时器
        self.signals = UpdateSignals()
        self.signals.update_ui.connect(self._update_ui)
        self.timer = QTimer()
        self.timer.timeout.connect(self.signals.update_ui.emit)
        self.timer.start(30)

        self._init_ui()

    # ---------- UI 初始化 ----------
    def _init_ui(self):
        central = QFrame()
        central.setStyleSheet("background: #F5F7FA; border-radius: 8px;")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题栏（可拖动）
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

        # 内容区域（含封面背景）
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(
            "background: transparent; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;"
        )
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        # 封面背景标签
        self.bg_label = QLabel(self.content_widget)
        self.bg_label.setScaledContents(True)
        self.bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bg_label.hide()
        self.bg_label.setGeometry(self.content_widget.rect())

        # 主分割器
        splitter = QSplitter(Qt.Horizontal)
        content_layout.addWidget(splitter, 1)

        # 左侧面板（歌词 + 条形图）
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

        # 条形图
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

        # 右侧面板（环形图）
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

        # 底部控制栏
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
        self.volume_slider.setRange(0, 30)
        self.volume_slider.setValue(15)
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

        # 平滑缓存初始化
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

    # ---------- 窗口控制 ----------
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

    # ---------- 封面背景 ----------
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

    # ---------- 文件选择 ----------
    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a);;All Files (*.*)"
        )
        if not path:
            return

        try:
            # 加载音频
            data, sr = librosa.load(path, sr=None, mono=True)
            self.audio_data = data.astype(np.float32)
            self.sample_rate = sr
            self.read_index = 0
            self.paused = False
            self.pause_btn.setText("⏸ 暂停")
            self.pause_btn.setEnabled(True)

            # 预计算 Mel 频谱
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

            # 歌词
            lrc_path = os.path.splitext(path)[0] + ".lrc"
            self.lyrics = parse_lrc(lrc_path)
            self.lyric_list.clear()
            for _, text in self.lyrics:
                item = QListWidgetItem(text)
                item.setForeground(QColor(44, 62, 80))
                self.lyric_list.addItem(item)
            if not self.lyrics:
                self.lyric_list.addItem("（无歌词）")
            self.current_lyric_index = -1

            # 歌曲名
            self.song_title_label.setText(os.path.splitext(os.path.basename(path))[0])

            # 封面
            covers = glob.glob(os.path.splitext(path)[0] + "_cover.*")
            self.cover_path = covers[0] if covers else None
            self._set_cover_background(self.cover_path)

            # 音频流
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

    # ---------- 音频回调 ----------
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

    # ---------- UI 更新 ----------
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

        # 清除旧高亮
        if self.current_lyric_index != -1:
            old = self.lyric_list.item(self.current_lyric_index)
            if old:
                old.setBackground(QColor(0, 0, 0, 0))
                old.setForeground(QColor(44, 62, 80))
                f = old.font()
                f.setBold(False)
                old.setFont(f)

        # 高亮新行
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

        # 平滑
        alpha = self.smooth_alpha
        self.smooth_bar_vals = alpha * raw + (1 - alpha) * self.smooth_bar_vals
        smoothed_bar = self.smooth_bar_vals

        # 环形采样
        ring_idx = np.linspace(0, self.fft_bins - 1, self.ring_bins, dtype=int)
        raw_ring = raw[ring_idx]
        self.smooth_ring_vals = alpha * raw_ring + (1 - alpha) * self.smooth_ring_vals
        smoothed_ring = self.smooth_ring_vals

        # 更新条形图
        cmap = plt.cm.viridis
        norm = Normalize(vmin=0, vmax=1)
        colors = cmap(norm(smoothed_bar))
        for rect, val, color in zip(self.bar_rects, smoothed_bar, colors):
            rect.set_height(val)
            rect.set_color(color)
        self.bar_ax.set_ylim(0, self.y_max)
        self.bar_canvas.draw_idle()

        # 更新环形图
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

    # ---------- 控制槽 ----------
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
        if self.stream:
            self.stream.stop()
            self.stream.close()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(245, 247, 250))
    pal.setColor(QPalette.WindowText, QColor(44, 62, 80))
    pal.setColor(QPalette.Base, QColor(255, 255, 255))
    pal.setColor(QPalette.AlternateBase, QColor(240, 245, 250))
    pal.setColor(QPalette.ToolTipBase, QColor(44, 62, 80))
    pal.setColor(QPalette.ToolTipText, QColor(44, 62, 80))
    pal.setColor(QPalette.Text, QColor(44, 62, 80))
    pal.setColor(QPalette.Button, QColor(232, 240, 254))
    pal.setColor(QPalette.ButtonText, QColor(44, 62, 80))
    pal.setColor(QPalette.BrightText, QColor(74, 144, 217))
    pal.setColor(QPalette.Highlight, QColor(74, 144, 217))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)

    window = AudioVisualizer()
    window.show()
    sys.exit(app.exec_())
