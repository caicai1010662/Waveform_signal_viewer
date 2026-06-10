"""
app.py — 主窗口

  MainWindow  : 顶栏控件 + 波形显示区 + 4 个滑动条 + 状态栏
                模式切换: Row / Tile / Oscilloscope
"""

import weakref

from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_BG, COLOR_TEXT, COLOR_ACCENT, COLOR_CARD,
                     COLOR_SEP, COLOR_HOVER, FONT_FAMILY, FONT_SIZE,
                     WINDOW_SEC, WINDOW_SEC_MIN, WINDOW_SEC_MAX,
                     AMP_SCALE_MIN, AMP_SCALE_MAX,
                     SPEED_MUL_MIN, SPEED_MUL_MAX)
from data import SignalData, LoaderWorker
from player import Player
from grid import GridView
from detail import DetailWindow
from oscilloscope import OscilloscopeView


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SignalViewer")
        self.resize(1600, 900)

        self._sd = SignalData()
        self._player = Player()
        self._player.frame_ready.connect(self._on_frame)
        self._player.state_changed.connect(self._on_state)

        self._details: weakref.WeakSet = weakref.WeakSet()
        self._loader: LoaderWorker = None
        self._mode = "row"   # "row" | "tile" | "scope"

        self._build()
        self._bind_keys()

    # ═══════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════

    def _build(self):
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        root = QtWidgets.QVBoxLayout(cw)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(4)

        # ── 顶栏 ──────────────────────────────────────────
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        bar.setSpacing(8)

        # 加载按钮
        self._btn_orig = QtWidgets.QPushButton("Load Original (.mat)")
        self._btn_orig.clicked.connect(self._load_orig)

        self._btn_recon = QtWidgets.QPushButton("Load Reconstructed (.mat)")
        self._btn_recon.clicked.connect(self._load_recon)
        self._btn_recon.setEnabled(False)

        bar.addWidget(self._btn_orig)
        bar.addWidget(self._btn_recon)

        # 分隔
        bar.addWidget(self._make_vsep())

        # 模式按钮（分段控件样式）
        seg_style = (
            "QPushButton {"
            "  border-radius: 0px; margin: 0px; padding: 5px 14px;"
            f" background: {COLOR_CARD}; color: {COLOR_TEXT};"
            f" border: 1px solid {COLOR_SEP};"
            "}"
            "QPushButton:checked {"
            f" background: {COLOR_ACCENT}; color: #FFFFFF;"
            f" border-color: {COLOR_ACCENT};"
            "}"
            "QPushButton:hover:!checked {"
            f" border-color: {COLOR_HOVER};"
            "}"
        )

        self._btn_row = QtWidgets.QPushButton("Row")
        self._btn_row.setCheckable(True)
        self._btn_row.setChecked(True)
        self._btn_row.setStyleSheet(seg_style + (
            "QPushButton { border-top-left-radius: 6px;"
            "border-bottom-left-radius: 6px; }"))

        self._btn_tile = QtWidgets.QPushButton("Tile")
        self._btn_tile.setCheckable(True)
        self._btn_tile.setStyleSheet(seg_style)

        self._btn_scope = QtWidgets.QPushButton("Scope")
        self._btn_scope.setCheckable(True)
        self._btn_scope.setStyleSheet(seg_style + (
            "QPushButton { border-top-right-radius: 6px;"
            "border-bottom-right-radius: 6px; }"))

        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self._btn_row, 0)
        mode_group.addButton(self._btn_tile, 1)
        mode_group.addButton(self._btn_scope, 2)
        mode_group.buttonClicked.connect(self._on_mode_change)

        bar.addWidget(self._btn_row)
        bar.addWidget(self._btn_tile)
        bar.addWidget(self._btn_scope)

        bar.addWidget(self._make_vsep())

        # 播放按钮
        self._btn_play = QtWidgets.QPushButton("▶  Play")
        self._btn_play.clicked.connect(self._player.toggle)
        self._btn_play.setEnabled(False)
        bar.addWidget(self._btn_play)

        self._btn_loop = QtWidgets.QPushButton("🔁 Loop")
        self._btn_loop.setCheckable(True)
        self._btn_loop.setChecked(True)
        self._btn_loop.clicked.connect(self._player.toggle_loop)
        self._btn_loop.setEnabled(False)
        self._player.loop_changed.connect(self._on_loop_changed)
        bar.addWidget(self._btn_loop)

        bar.addStretch(1)

        # 时窗：Time: [50ms] ─━─
        lbl_time_title = QtWidgets.QLabel("Time:")
        lbl_time_title.setStyleSheet(f"color: {COLOR_TEXT};")
        bar.addWidget(lbl_time_title)
        self._lbl_win = self._make_info_label("50ms")
        bar.addWidget(self._lbl_win)
        self._slider_win = self._make_h_slider()
        self._slider_win.valueChanged.connect(self._on_win_slider)
        bar.addWidget(self._slider_win)

        # 幅值：Amp: [1.0×] ─━─
        lbl_amp_title = QtWidgets.QLabel("Amp:")
        lbl_amp_title.setStyleSheet(f"color: {COLOR_TEXT};")
        bar.addWidget(lbl_amp_title)
        self._lbl_amp = self._make_info_label("1.0×")
        bar.addWidget(self._lbl_amp)
        self._slider_amp = self._make_h_slider()
        self._slider_amp.valueChanged.connect(self._on_amp_slider)
        bar.addWidget(self._slider_amp)

        # 速度：Speed: [1.0×] ─━─
        lbl_speed_title = QtWidgets.QLabel("Speed:")
        lbl_speed_title.setStyleSheet(f"color: {COLOR_TEXT};")
        bar.addWidget(lbl_speed_title)
        self._lbl_speed = self._make_info_label("1.0×")
        bar.addWidget(self._lbl_speed)
        self._slider_speed = self._make_h_slider()
        self._slider_speed.valueChanged.connect(self._on_speed_slider)
        bar.addWidget(self._slider_speed)

        root.addLayout(bar)

        # ── 分隔线 ────────────────────────────────────────
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── 波形显示区 ────────────────────────────────────
        wave_row = QtWidgets.QHBoxLayout()
        wave_row.setContentsMargins(0, 4, 0, 0)
        wave_row.setSpacing(4)

        # 网格视图 (Row / Tile)
        self._grid = GridView(self._sd)
        self._grid.channel_clicked.connect(self._open_detail)

        # 示波器视图
        self._scope = OscilloscopeView(self._sd)
        self._scope.channel_clicked.connect(self._open_detail)

        # 模式堆叠
        self._view_stack = QtWidgets.QStackedLayout()
        self._view_stack.addWidget(self._grid)
        self._view_stack.addWidget(self._scope)
        self._view_stack.setCurrentIndex(0)

        wave_row.addLayout(self._view_stack, 1)

        # 通道竖向滑动条
        self._slider_ch = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self._slider_ch.setMinimum(0)
        self._slider_ch.setMaximum(0)
        self._slider_ch.setInvertedAppearance(True)
        self._slider_ch.setInvertedControls(True)
        self._slider_ch.setFixedWidth(18)
        self._slider_ch.valueChanged.connect(self._on_ch_scroll)
        self._slider_ch.setEnabled(False)
        wave_row.addWidget(self._slider_ch)

        root.addLayout(wave_row, 1)

        # ── 状态栏 ────────────────────────────────────────
        self._status = QtWidgets.QLabel("Ready")
        self._status.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}'; "
            f"font-size: {FONT_SIZE}px; padding: 4px 8px;")
        root.addWidget(self._status)

        # 初始化滑动条默认值
        self._reset_sliders()

    @staticmethod
    def _make_h_slider() -> QtWidgets.QSlider:
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        s.setRange(0, 1000)
        s.setFixedWidth(100)
        s.setEnabled(False)
        return s

    @staticmethod
    def _make_vsep() -> QtWidgets.QFrame:
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        f.setFixedWidth(1)
        return f

    def _make_info_label(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}'; "
            f"font-size: 10px; padding: 2px 4px; "
            f"background: {COLOR_CARD}; border-radius: 4px;")
        lbl.setFixedWidth(40)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        return lbl

    def _reset_sliders(self):
        """设置滑动条到默认值。"""
        # 时窗: 默认 50ms, 映射 [10ms, 200ms]
        self._slider_win.setValue(
            int((WINDOW_SEC - WINDOW_SEC_MIN) /
                (WINDOW_SEC_MAX - WINDOW_SEC_MIN) * 1000))
        # 幅值: 默认 1.0×, 映射 [0.2×, 5.0×]
        self._slider_amp.setValue(
            int((1.0 - AMP_SCALE_MIN) /
                (AMP_SCALE_MAX - AMP_SCALE_MIN) * 1000))
        # 速度: 默认 1.0×, 映射 [0.1×, 10.0×]
        self._slider_speed.setValue(
            int((1.0 - SPEED_MUL_MIN) /
                (SPEED_MUL_MAX - SPEED_MUL_MIN) * 1000))

    # ═══════════════════════════════════════════════════════════
    # 键盘快捷键
    # ═══════════════════════════════════════════════════════════

    def _bind_keys(self):
        S = QtWidgets.QShortcut
        K = QtCore.Qt
        Q = QtGui.QKeySequence

        S(Q(K.Key_Space), self, activated=lambda: self._player.toggle())
        S(Q(K.Key_Up), self, activated=lambda: self._slider_ch.setValue(
            max(0, self._slider_ch.value() - 1)))
        S(Q(K.Key_Down), self, activated=lambda: self._slider_ch.setValue(
            min(self._slider_ch.maximum(), self._slider_ch.value() + 1)))
        S(Q(K.Key_Left), self, activated=lambda: self._player.seek_delta(
            -max(1, self._sd.window_pts // 20)))
        S(Q(K.Key_Right), self, activated=lambda: self._player.seek_delta(
            max(1, self._sd.window_pts // 20)))
        S(Q("Ctrl+Up"), self, activated=self._player.speed_up)
        S(Q("Ctrl+Down"), self, activated=self._player.speed_down)
        S(Q("Ctrl+R"), self, activated=self._cycle_mode)

    # ═══════════════════════════════════════════════════════════
    # 模式切换
    # ═══════════════════════════════════════════════════════════

    def _on_mode_change(self, btn):
        mode_map = {self._btn_row: "row",
                     self._btn_tile: "tile",
                     self._btn_scope: "scope"}
        new_mode = mode_map.get(btn, "row")
        if new_mode == self._mode:
            return
        self._mode = new_mode

        if new_mode == "scope":
            self._view_stack.setCurrentIndex(1)
            if self._sd.ready:
                self._scope.set_channel_range(0, 8)
        else:
            self._view_stack.setCurrentIndex(0)
            self._grid.set_mode(new_mode)
            # 重建 grid 数据
            if self._sd.ready:
                self._grid.build()
                self._slider_ch.setMaximum(max(0, self._sd.max_channel_offset))

        self._update_status()

    def _cycle_mode(self):
        """Ctrl+R 循环切换模式。"""
        modes = ["row", "tile", "scope"]
        idx = modes.index(self._mode)
        next_mode = modes[(idx + 1) % 3]
        btn_map = {"row": self._btn_row,
                    "tile": self._btn_tile,
                    "scope": self._btn_scope}
        btn_map[next_mode].setChecked(True)

    # ═══════════════════════════════════════════════════════════
    # 加载
    # ═══════════════════════════════════════════════════════════

    def _load_orig(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Original .mat File", "",
            "MAT Files (*.mat);;All (*)")
        if not path:
            return

        def on_done(data, s_freq, raw_path):
            self._sd.orig = data
            self._sd.orig_path = raw_path or path
            self._sd.s_freq = s_freq
            self._sd.n_chan = data.shape[0]
            self._sd.n_samples = data.shape[1]
            self._btn_recon.setEnabled(True)
            self._update_status()

        self._load_mat_async(path, "Loading Original Signal", on_done)

    def _load_recon(self):
        if self._sd.orig is None:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Reconstructed .mat File", "",
            "MAT Files (*.mat);;All (*)")
        if not path:
            return

        def on_done(recon, _s_freq, raw_path):
            try:
                # 通道校验
                if recon.shape[0] != self._sd.n_chan:
                    if recon.shape[1] == self._sd.n_chan:
                        recon = recon.T
                    else:
                        raise ValueError(
                            f"Channel count mismatch! "
                            f"Original: {self._sd.n_chan}, "
                            f"Reconstructed: {recon.shape[0]}")

                # 长度对齐
                min_len = min(self._sd.n_samples, recon.shape[1])
                if self._sd.orig.shape[1] > min_len:
                    self._sd.orig = self._sd.orig[:, :min_len]
                self._sd.recon = recon[:, :min_len]
                self._sd.recon_path = raw_path or path
                self._sd.n_samples = min_len

                # 计算参数
                self._sd.compute_params()

                # 构建视图
                if self._mode == "scope":
                    self._scope.set_channel_range(0, 8)
                else:
                    self._grid.set_mode(self._mode)
                    self._grid.build()

                # 配置播放器
                self._player.configure(
                    self._sd.s_freq, self._sd.n_samples,
                    self._sd.window_pts)
                self._player.seek(0)

                # 启用控件
                self._slider_ch.setMaximum(max(0, self._sd.max_channel_offset))
                self._slider_ch.setValue(0)
                self._btn_play.setEnabled(True)
                self._btn_loop.setEnabled(True)
                self._slider_win.setEnabled(True)
                self._slider_amp.setEnabled(True)
                self._slider_speed.setEnabled(True)
                self._slider_ch.setEnabled(True)

                self._reset_sliders()
                self._update_status()

            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Error", f"Loading failed:\n{e}")

        self._load_mat_async(path, "Loading Reconstructed Signal", on_done)

    def _load_mat_async(self, path: str, title: str, on_done):
        """异步加载 .mat，显示进度弹窗。"""
        dlg = QtWidgets.QProgressDialog("Loading...", None, 0, 0, self)
        dlg.setWindowTitle(title)
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show()

        self._loader = LoaderWorker(path)
        self._loader.progress.connect(dlg.setLabelText)
        self._loader.finished.connect(
            lambda d, f, r: (dlg.close(), on_done(d, f, r)))
        self._loader.error_msg.connect(
            lambda e: (dlg.close(),
                       QtWidgets.QMessageBox.critical(
                           self, "Error", f"Loading failed:\n{e}")))
        self._loader.start()

    # ═══════════════════════════════════════════════════════════
    # 帧更新
    # ═══════════════════════════════════════════════════════════

    def _on_frame(self):
        if not self._sd.ready:
            return
        ptr = self._player.ptr
        if ptr + self._sd.window_pts > self._sd.n_samples:
            return
        if self._mode == "scope":
            self._scope.scroll(ptr, self._sd)
        else:
            self._grid.scroll(ptr, self._sd)
        self._player.ack()

    def _on_state(self, playing: bool):
        self._btn_play.setText("⏸  Pause" if playing else "▶  Play")

    def _on_loop_changed(self, looping: bool):
        self._btn_loop.setText("🔁 Loop" if looping else "🔁 One-Shot")
        self._btn_loop.setChecked(looping)

    # ═══════════════════════════════════════════════════════════
    # 滑动条回调
    # ═══════════════════════════════════════════════════════════

    def _on_ch_scroll(self, val: int):
        if not self._sd.ready:
            return
        if self._mode != "scope":
            self._grid.set_offset(self._sd, val)

    def _on_win_slider(self, val: int):
        """时窗滑动条: 0-1000 → 10ms-200ms。"""
        if not self._sd.ready:
            return
        frac = val / 1000.0
        sec = WINDOW_SEC_MIN + frac * (WINDOW_SEC_MAX - WINDOW_SEC_MIN)
        self._sd.set_window(sec)
        self._lbl_win.setText(f"{sec * 1000:.0f}ms")

        if self._mode != "scope":
            self._grid.update_ranges(self._sd)
        self._player.configure(
            self._sd.s_freq, self._sd.n_samples, self._sd.window_pts)
        self._player.seek(self._player.ptr)
        self._update_details()

    def _on_amp_slider(self, val: int):
        """幅值滑动条: 0-1000 → 0.2×-5.0×。"""
        if not self._sd.ready:
            return
        frac = val / 1000.0
        scale = AMP_SCALE_MIN + frac * (AMP_SCALE_MAX - AMP_SCALE_MIN)
        self._sd.set_amp_scale(scale)
        self._lbl_amp.setText(f"{scale:.1f}×")

        if self._mode != "scope":
            self._grid.reload_amp(self._sd)
        self._update_details()

    def _on_speed_slider(self, val: int):
        """速度滑动条: 0-1000 → 0.1×-10.0×。"""
        frac = val / 1000.0
        mul = SPEED_MUL_MIN + frac * (SPEED_MUL_MAX - SPEED_MUL_MIN)
        self._player.set_speed(mul)
        self._lbl_speed.setText(f"{mul:.1f}×")

    # ═══════════════════════════════════════════════════════════
    # 详情窗口
    # ═══════════════════════════════════════════════════════════

    def _open_detail(self, ch: int):
        for ref in list(self._details):
            dw = ref
            if dw is not None and dw._ch == ch:
                try:
                    dw.activateWindow()
                    dw.raise_()
                    return
                except RuntimeError:
                    pass

        dw = DetailWindow(ch, self._sd, self._player, parent=self)
        dw.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        dw.setWindowFlag(QtCore.Qt.Window, True)
        dw.move(self.x() + 30, self.y() + 30)
        dw.show()
        self._details.add(dw)

    def _update_details(self):
        """同步时窗/幅值变化到所有打开的详情窗。"""
        for ref in list(self._details):
            dw = ref
            if dw is not None:
                try:
                    dw.update_ranges()
                except RuntimeError:
                    pass

    # ═══════════════════════════════════════════════════════════
    # 状态
    # ═══════════════════════════════════════════════════════════

    def _update_status(self):
        if self._sd.ready:
            self._status.setText(
                f"Ch 1-{self._sd.n_chan}  |  "
                f"{self._sd.s_freq / 1000:.0f} kHz  |  "
                f"{self._sd.n_samples / self._sd.s_freq:.1f}s  |  "
                f"Mode: {self._mode.title()}")
        elif self._sd.orig is not None:
            self._status.setText(
                f"Original loaded: Ch 1-{self._sd.n_chan}  |  "
                f"{self._sd.s_freq / 1000:.0f} kHz  |  "
                f"Awaiting reconstructed...")
        else:
            self._status.setText("Ready — Load original .mat file to begin")
