"""
app.py — 主窗口（顶层组装器）

  MainWindow : 将 grid / player / data 组装成完整 UI。
               负责: 顶栏控件、3 个滑动条、键盘快捷键、文件加载、详情窗管理。

  这是用户直接交互的窗口。所有控件信号在这里连接到对应的处理逻辑。

  调参入口:
    滑动条范围 → _on_win_slider / _on_amp_slider / _on_speed_slider 中的映射公式
    滑动条外观 → _make_h_slider() / _slider_ch 的 setFixedWidth
    数值框样式 → _make_info_label()
    标签样式 → 搜 "Time:" / "Amp:" / "Speed:"
    默认值   → _reset_sliders()
"""

import weakref

from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_TEXT, FONT_FAMILY,
                     WIN_WIDTH, WIN_HEIGHT, WIN_X, WIN_Y,
                     WIN_MAXIMIZED, WIN_TITLE)
from data import (SignalData, LoaderWorker,
                   WINDOW_SEC, WINDOW_SEC_MIN, WINDOW_SEC_MAX,
                   AMP_SCALE_MIN, AMP_SCALE_MAX)
from player import Player, SPEED_MUL_MIN, SPEED_MUL_MAX
from grid import GridView, VISIBLE_ROWS, TILE_COLS, VISIBLE_TILE_ROWS
from detail import DetailWindow, DETAIL_OFFSET_X, DETAIL_OFFSET_Y


class MainWindow(QtWidgets.QMainWindow):
    """SignalViewer 主窗口。

    布局:
      ┌─────────────────────────────────────────────┐
      │ [Load Signal] | [Compare][Browse] |         │
      │ [Start] [Loop]    Time: [50ms] ─━─          │ ← 顶栏
      │                   Amp: [1.0×] ─━─           │
      │                   Speed:[1.0×] ─━─           │
      ├─────────────────────────────────────────────┤
      │ ┌─────────────────────────────────┐ ┌────┐ │
      │ │          Signal                  │ │通道│ │ ← 波形区
      │ └─────────────────────────────────┘ └────┘ │
      └─────────────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WIN_TITLE)
        self.resize(WIN_WIDTH, WIN_HEIGHT)
        # 窗口位置：WIN_X/WIN_Y ≥0 时指定坐标，否则由 OS 决定
        if WIN_X >= 0 and WIN_Y >= 0:
            self.move(WIN_X, WIN_Y)
        if WIN_MAXIMIZED:
            self.showMaximized()

        # ── 核心对象 ─────────────────────────────────────
        self._sd = SignalData()          # 数据容器
        self._player = Player()          # 播放引擎

        # ── 连接播放信号 ─────────────────────────────────
        self._player.frame_ready.connect(self._on_frame)
        self._player.state_changed.connect(self._on_state)

        # ── 状态 ─────────────────────────────────────────
        self._details: weakref.WeakSet = weakref.WeakSet()  # 详情窗弱引用集
        self._loader: LoaderWorker = None                   # 当前异步加载线程
        self._mode = "row"  # 当前显示模式: "row" | "tile"

        # ── 通道滑块短防抖（30ms）─────────────────────────
        self._ch_timer = QtCore.QTimer()
        self._ch_timer.setSingleShot(True)
        self._ch_timer.setInterval(30)
        self._ch_timer.timeout.connect(self._apply_ch_offset)

        self._build()
        self._bind_keys()

    # ═══════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════

    def _build(self):
        """构建完整的窗口 UI。只执行一次。"""
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        root = QtWidgets.QVBoxLayout(cw)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(4)

        # ══ 顶栏 ══════════════════════════════════════════
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        bar.setSpacing(8)

        # ── 文件加载 ──────────────────────────────────────
        self._btn_load = QtWidgets.QPushButton("Load Data")
        self._btn_load.clicked.connect(self._load_signal)

        bar.addWidget(self._btn_load)
        bar.addWidget(self._make_vsep())

        # ── 模式切换按钮（三段式）─────────────────────────
        # 无专属样式，完全继承 config.py 全局按钮风格
        self._btn_row = QtWidgets.QPushButton("Trace")
        self._btn_row.setCheckable(True)
        self._btn_row.setChecked(True)

        self._btn_tile = QtWidgets.QPushButton("Grid")
        self._btn_tile.setCheckable(True)

        # QButtonGroup 保证两者互斥
        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self._btn_row, 0)
        mode_group.addButton(self._btn_tile, 1)
        mode_group.buttonClicked.connect(self._on_mode_change)

        bar.addWidget(self._btn_row)
        bar.addWidget(self._btn_tile)
        bar.addWidget(self._make_vsep())

        # ── 播放控制按钮 ──────────────────────────────────
        self._btn_play = QtWidgets.QPushButton("Start")
        self._btn_play.clicked.connect(self._player.toggle)
        self._btn_play.setEnabled(False)

        self._btn_loop = QtWidgets.QPushButton("Loop")
        self._btn_loop.setCheckable(True)
        self._btn_loop.setChecked(True)          # 默认循环模式
        self._btn_loop.clicked.connect(self._player.toggle_loop)
        self._btn_loop.setEnabled(False)
        self._player.loop_changed.connect(self._on_loop_changed)

        bar.addWidget(self._btn_play)
        bar.addWidget(self._btn_loop)

        # 元信息标签 — 加载数据后显示通道数/采样率/总时长
        self._lbl_info = QtWidgets.QLabel("")
        self._lbl_info.setStyleSheet(
            f"color: #808080; font-size: 16px; font-weight: bold;")
        bar.addWidget(self._lbl_info)

        bar.addStretch(1)  # 弹簧 — 把右侧滑块推到最右边

        # ── 时窗滑动条组 ──────────────────────────────────
        # 改标签文字: 修改 "Time:" 字符串
        # 改标签样式: 修改 setStyleSheet 中的 color / font-size
        # 改数值框样式: 找到 _make_info_label() 方法
        lbl_time_title = QtWidgets.QLabel("Time:")
        lbl_time_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 22px; font-weight: bold;")
        bar.addWidget(lbl_time_title)

        self._lbl_win = self._make_info_label("50ms")  # 数值框
        self._lbl_win.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 20px; font-weight: bold;")
        bar.addWidget(self._lbl_win)

        self._slider_win = self._make_h_slider()       # 滑条
        self._slider_win.valueChanged.connect(self._on_win_slider)
        self._slider_win.sliderReleased.connect(self._on_win_released)
        bar.addWidget(self._slider_win)

        # ── 幅值滑动条组 ──────────────────────────────────
        lbl_amp_title = QtWidgets.QLabel("  Amp:")
        lbl_amp_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 22px; font-weight: bold;")
        bar.addWidget(lbl_amp_title)

        self._lbl_amp = self._make_info_label("1.0×")
        self._lbl_amp.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 20px; font-weight: bold;")
        bar.addWidget(self._lbl_amp)

        self._slider_amp = self._make_h_slider()
        self._slider_amp.valueChanged.connect(self._on_amp_slider)
        self._slider_amp.sliderReleased.connect(self._on_amp_released)
        bar.addWidget(self._slider_amp)

        # ── 速度滑动条组 ──────────────────────────────────
        lbl_speed_title = QtWidgets.QLabel("  Speed:")
        lbl_speed_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 22px; font-weight: bold;")
        bar.addWidget(lbl_speed_title)

        self._lbl_speed = self._make_info_label("1.0×")
        self._lbl_speed.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 20px; font-weight: bold;")
        bar.addWidget(self._lbl_speed)

        self._slider_speed = self._make_h_slider()
        self._slider_speed.valueChanged.connect(self._on_speed_slider)
        bar.addWidget(self._slider_speed)

        # ── 绝对时间戳（顶栏最右侧）──────────────────────
        self._lbl_timestamp = QtWidgets.QLabel("00m 00.000s")
        self._lbl_timestamp.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 18px; font-weight: bold;")
        bar.addWidget(self._lbl_timestamp)

        root.addLayout(bar)

        # ══ 分隔线 ════════════════════════════════════════
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("border: none; background-color: #474748;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ══ 波形显示区 ════════════════════════════════════
        wave_row = QtWidgets.QHBoxLayout()
        wave_row.setContentsMargins(0, 4, 8, 4)  # 右侧留 8px 防止滚动条贴墙
        wave_row.setSpacing(4)

        # GridView — 管理 Compare (Row) 和 Browse (Tile) 两种模式
        self._grid = GridView(self._sd)
        self._grid.channel_clicked.connect(self._open_detail)

        wave_row.addWidget(self._grid, 1)

        # 右侧通道浏览滑动条
        # 改粗细: setFixedWidth(18 → 更大/更小)
        # 改范围: setMaximum 在 _load_recon 中动态设置
        self._slider_ch = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self._slider_ch.setMinimum(0)
        self._slider_ch.setMaximum(0)              # 加载数据后更新
        self._slider_ch.setInvertedAppearance(True) # 向上拖 = 值增大
        self._slider_ch.setInvertedControls(True)
        self._slider_ch.setFixedWidth(22)           # 滑条宽度（与 QSS groove width 一致）
        self._slider_ch.valueChanged.connect(self._on_ch_scroll)
        self._slider_ch.sliderReleased.connect(self._on_ch_released)
        self._slider_ch.setEnabled(False)
        wave_row.addWidget(self._slider_ch)

        root.addLayout(wave_row, 1)

        # 初始化滑动条到默认值
        self._reset_sliders()

    # ═══════════════════════════════════════════════════════════
    # 小部件工厂方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _make_h_slider() -> QtWidgets.QSlider:
        """创建水平滑动条。

        改长度: setFixedWidth(200)
        改范围: setRange(0, 1000) — 内部 0-1000 映射到实际值
        """
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        s.setRange(0, 1000)
        s.setFixedWidth(200)
        s.setEnabled(False)
        return s

    @staticmethod
    def _make_vsep() -> QtWidgets.QFrame:
        """创建垂直分隔线。"""
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setStyleSheet("border: none; background-color: #474748;")
        f.setFixedWidth(1)
        return f

    def _make_info_label(self, text: str) -> QtWidgets.QLabel:
        """创建数值显示框（如 "50ms"、"1.0×"）。

        改颜色: color / background
        改字号: font-size
        改宽度: setFixedWidth(55)
        """
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(
            f"color: #FFFFFF; font-family: '{FONT_FAMILY}'; "
            f"font-size: 13px; font-weight: bold; padding: 4px 6px; "
            f"background: #252526; border: 1px solid #3E3E42; border-radius: 4px;")
        lbl.setFixedWidth(55)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        return lbl

    def _reset_sliders(self):
        """将三个水平滑动条设置到默认值。

        时窗默认 50ms，幅值默认 1.0×，速度默认 1.0×。
        滑块值 0-1000 按比例映射到 MIN-MAX 范围。
        """
        # 时窗: 默认 WINDOW_SEC=50ms
        self._slider_win.setValue(
            int((WINDOW_SEC - WINDOW_SEC_MIN) /
                (WINDOW_SEC_MAX - WINDOW_SEC_MIN) * 1000))
        # 幅值: 默认 1.0×
        self._slider_amp.setValue(
            int((1.0 - AMP_SCALE_MIN) /
                (AMP_SCALE_MAX - AMP_SCALE_MIN) * 1000))
        # 速度: 默认 1.0×
        self._slider_speed.setValue(
            int((1.0 - SPEED_MUL_MIN) /
                (SPEED_MUL_MAX - SPEED_MUL_MIN) * 1000))

    # ═══════════════════════════════════════════════════════════
    # 键盘快捷键
    # ═══════════════════════════════════════════════════════════

    def _bind_keys(self):
        """绑定键盘快捷键。"""
        S = QtWidgets.QShortcut
        K = QtCore.Qt
        KS = QtGui.QKeySequence

        S(KS(K.Key_Space), self,
          activated=lambda: self._player.toggle())              # 播放/暂停
        S(KS(K.Key_Left), self,
          activated=lambda: self._player.seek_delta(-300))     # ← 步退 10ms
        S(KS(K.Key_Right), self,
          activated=lambda: self._player.seek_delta(300))      # → 步进 10ms
        S(KS(K.Key_Up), self,
          activated=self._ch_up)                                # ↑ 上滚通道
        S(KS(K.Key_Down), self,
          activated=self._ch_down)                              # ↓ 下滚通道
        S(KS(K.Key_Up | K.CTRL), self,
          activated=lambda: self._player.speed_up())           # Ctrl+↑ 加速
        S(KS(K.Key_Down | K.CTRL), self,
          activated=lambda: self._player.speed_down())         # Ctrl+↓ 减速

    # ═══════════════════════════════════════════════════════════
    # 模式切换
    # ═══════════════════════════════════════════════════════════

    def _on_mode_change(self, btn):
        """模式按钮点击回调。QButtonGroup 保证互斥。

        切换时保持当前通道位置，而非归零。
        """
        mode_map = {self._btn_row: "row",
                     self._btn_tile: "tile"}
        new_mode = mode_map.get(btn, "row")
        if new_mode == self._mode:
            return

        # 保存当前通道位置
        saved_offset = self._slider_ch.value()

        self._mode = new_mode
        self._grid.set_mode(new_mode)
        if self._sd.ready:
            per_page = (VISIBLE_ROWS if new_mode == "row"
                        else TILE_COLS * VISIBLE_TILE_ROWS)
            slider_max = self._sd.max_channel_offset(per_page)
            self._slider_ch.blockSignals(True)
            self._slider_ch.setMaximum(slider_max)
            self._slider_ch.setValue(min(saved_offset, slider_max))
            self._slider_ch.blockSignals(False)
            # 通知 grid 更新到当前位置（set_mode 内已 build，这里只同步 offset）
            self._grid.set_offset(self._sd, self._slider_ch.value())

    def _load_signal(self):
        """加载/重载信号 .mat 文件 → 计算幅值 → 构建视图 → 启用控件。"""
        self._player.pause()  # 先停止播放，防止换文件时状态混乱
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Signal .mat File", "",
            "MAT Files (*.mat);;All (*)")
        if not path:
            return

        def on_done(data, s_freq, raw_path):
            try:
                self._sd.recon = data
                self._sd.recon_path = raw_path or path
                self._sd.s_freq = s_freq
                self._sd.n_chan = data.shape[0]
                self._sd.n_samples = data.shape[1]

                self._sd.compute_params()

                total_s = self._sd.n_samples / self._sd.s_freq
                self._lbl_info.setText(
                    f"{self._sd.n_chan}ch · "
                    f"{self._sd.s_freq / 1000:.0f}kSa/s · "
                    f"{total_s:.1f}s")

                self._grid.set_mode(self._mode)
                self._grid.build()

                self._player.configure(
                    self._sd.s_freq, self._sd.n_samples,
                    self._sd.window_pts)
                self._player.seek(0)

                self._slider_ch.setMaximum(
                    self._sd.max_channel_offset(VISIBLE_ROWS))
                self._slider_ch.setValue(0)
                self._btn_play.setEnabled(True)
                self._btn_loop.setEnabled(True)
                self._slider_win.setEnabled(True)
                self._slider_amp.setEnabled(True)
                self._slider_speed.setEnabled(True)
                self._slider_ch.setEnabled(True)

                self._reset_sliders()

            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Error", f"Loading failed:\n{e}")

        self._load_mat_async(path, "Loading Signal", on_done)

    def _load_mat_async(self, path: str, title: str, on_done):
        """异步加载 .mat 文件。

        显示一个模态进度对话框（不停旋转的进度条），
        LoaderWorker 在后台线程中执行实际加载。
        完成后自动关闭对话框并调用 on_done 回调。

        加载锁: 已有线程在运行时忽略重复点击，防止并发加载
        导致 self._loader 被覆盖、旧线程信号连到已销毁对话框。
        """
        if self._loader is not None and self._loader.isRunning():
            return  # 已有加载任务在进行中，忽略重复点击
        dlg = QtWidgets.QProgressDialog("Loading...", None, 0, 0, self)
        dlg.setWindowTitle(title)
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.setCancelButton(None)        # 不允许取消
        dlg.setMinimumDuration(0)        # 立即显示
        dlg.show()

        self._loader = LoaderWorker(path)
        self._loader.progress.connect(dlg.setLabelText)     # 更新进度文字
        self._loader.finished.connect(
            lambda d, f, r: (dlg.close(), on_done(d, f, r)))
        self._loader.error_msg.connect(
            lambda e: (dlg.close(),
                       QtWidgets.QMessageBox.critical(
                           self, "Error", f"Loading failed:\n{e}")))
        self._loader.start()

    # ═══════════════════════════════════════════════════════════
    # 帧更新 — Player.frame_ready 的回调
    # ═══════════════════════════════════════════════════════════

    def _on_frame(self):
        """播放器每帧回调。将当前 ptr 分发给 GridView。

        流程:
          1. Player._tick() → frame_ready(ptr)
          2. _on_frame → grid.scroll(ptr)
          3. Player.ack() → 释放 _pending 锁

        防御设计:
          - 所有出口（正常/越界/异常）都调 ack()。
          - finally 块保证即使 grid.scroll 抛异常，_pending 也不会永久卡死。
          - 边界检查在 try 之前：ptr 越界时手动调 ack() 后 return，
            不依赖 try/finally 的隐式覆盖。
        """
        if not self._sd.ready:
            return
        ptr = self._player.ptr
        # ── 边界保护：数据末尾时窗口可能超出范围 ──
        if ptr + self._sd.window_pts > self._sd.n_samples:
            self._player.ack()
            return
        try:
            self._grid.scroll(ptr, self._sd)
            # 更新绝对时间戳
            abs_sec = ptr / self._sd.s_freq
            mins, sec = divmod(abs_sec, 60)
            self._lbl_timestamp.setText( f"{int(mins):02d}m {sec:06.3f}s")
        finally:
            self._player.ack()

    def _on_state(self, playing: bool):
        """播放状态变化 → 更新按钮文字。"""
        self._btn_play.setText("Pause" if playing else "Start")

    def _on_loop_changed(self, looping: bool):
        """循环模式变化 → 更新 Loop 按钮。"""
        self._btn_loop.setText("Loop" if looping else "Once")
        self._btn_loop.setChecked(looping)

    # ═══════════════════════════════════════════════════════════
    # 滑动条回调 — 用户拖动滑块时触发
    #   每个回调做三件事: 更新 SignalData → 更新视图 → 更新标签文字
    # ═══════════════════════════════════════════════════════════

    def _apply_ch_offset(self):
        """执行通道切换 — 用滑动条当前值更新 grid 视口。"""
        if self._sd.ready:
            self._grid.set_offset(self._sd, self._slider_ch.value())

    def _on_ch_scroll(self, val: int):
        """通道滑动条拖动中 — 启动 30ms 短防抖定时器。"""
        if self._sd.ready:
            self._ch_timer.start()

    def _on_ch_released(self):
        """松手时立即执行，不等防抖。"""
        self._ch_timer.stop()
        self._apply_ch_offset()

    def _ch_up(self):
        """↑ 键 — 向上滚动一个通道。"""
        if self._slider_ch.isEnabled():
            v = max(0, self._slider_ch.value() - 1)
            self._slider_ch.setValue(v)

    def _ch_down(self):
        """↓ 键 — 向下滚动一个通道。"""
        if self._slider_ch.isEnabled():
            v = min(self._slider_ch.maximum(),
                    self._slider_ch.value() + 1)
            self._slider_ch.setValue(v)

    def _on_win_slider(self, val: int):
        """时窗滑动条拖动中 — 只更新数值标签，保证手感丝滑。"""
        if not self._sd.ready:
            return
        frac = val / 1000.0
        sec = WINDOW_SEC_MIN + frac * (WINDOW_SEC_MAX - WINDOW_SEC_MIN)
        self._sd.set_window(sec)
        self._lbl_win.setText(f"{sec * 1000:.0f}ms")

    def _on_win_released(self):
        """时窗滑动条松手 — 一次性执行耗时的 grid 重载。"""
        if not self._sd.ready:
            return
        self._grid.update_ranges(self._sd)
        self._player.configure(
            self._sd.s_freq, self._sd.n_samples, self._sd.window_pts)
        self._player.seek(self._player.ptr)
        self._update_details()

    def _on_amp_slider(self, val: int):
        """幅值滑动条拖动中 — 只更新数值标签，保证手感丝滑。"""
        if not self._sd.ready:
            return
        frac = val / 1000.0
        scale = AMP_SCALE_MIN + frac * (AMP_SCALE_MAX - AMP_SCALE_MIN)
        self._sd.set_amp_scale(scale)
        self._lbl_amp.setText(f"{scale:.1f}×")

    def _on_amp_released(self):
        """幅值滑动条松手 — 一次性执行耗时的 grid 重载。"""
        if not self._sd.ready:
            return
        self._grid.reload_amp(self._sd)
        self._update_details()

    def _on_speed_slider(self, val: int):
        """速度滑动条: 0-1000 → SPEED_MUL_MIN ~ SPEED_MUL_MAX。

        改范围: 修改 config.py 的 SPEED_MUL_MIN / MAX。
        """
        frac = val / 1000.0
        mul = SPEED_MUL_MIN + frac * (SPEED_MUL_MAX - SPEED_MUL_MIN)
        self._player.set_speed(mul)
        self._lbl_speed.setText(f"{mul:.1f}×")

    # ═══════════════════════════════════════════════════════════
    # 详情窗口管理
    # ═══════════════════════════════════════════════════════════

    def _open_detail(self, ch: int):
        """打开/激活通道 ch 的详情窗口。

        同一个通道已经在打开 → 激活已有窗口（不重复创建）。
        使用 WeakSet 存储，窗口关闭后自动回收。
        """
        # 检查是否已有该通道的窗口
        for ref in list(self._details):
            dw = ref
            if dw is not None and dw._ch == ch:
                try:
                    dw.activateWindow()
                    dw.raise_()
                    return
                except RuntimeError:
                    pass

        # 创建新窗口
        dw = DetailWindow(ch, self._sd, self._player, parent=self)
        dw.setAttribute(QtCore.Qt.WA_DeleteOnClose)       # 关闭时自动销毁
        dw.setWindowFlag(QtCore.Qt.Window, True)          # 独立窗口（非子窗口）
        dw.move(self.x() + DETAIL_OFFSET_X,
                self.y() + DETAIL_OFFSET_Y)
        dw.show()
        self._details.add(dw)

    def _update_details(self):
        """时窗/幅值变化 → 同步到所有打开的详情窗口。"""
        for ref in list(self._details):
            dw = ref
            if dw is not None:
                try:
                    dw.update_ranges()
                except RuntimeError:
                    pass

