"""
app.py — 主窗口（顶层组装器）

  MainWindow : 将 grid / oscilloscope / player / data 组装成完整 UI。
               负责: 顶栏控件、4 个滑动条、键盘快捷键、文件加载、详情窗管理。

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

from config import (COLOR_BG, COLOR_TEXT, COLOR_ACCENT, COLOR_CARD,
                     COLOR_SEP, COLOR_HOVER, COLOR_ORIG, FONT_FAMILY, FONT_SIZE,
                     WINDOW_SEC, WINDOW_SEC_MIN, WINDOW_SEC_MAX,
                     AMP_SCALE_MIN, AMP_SCALE_MAX,
                     SPEED_MUL_MIN, SPEED_MUL_MAX)
from data import SignalData, LoaderWorker
from player import Player
from grid import GridView
from detail import DetailWindow
from oscilloscope import OscilloscopeView


class MainWindow(QtWidgets.QMainWindow):
    """SignalViewer 主窗口。

    布局:
      ┌─────────────────────────────────────────────┐
      │ [Load] [Load] | [Compare][Browse][Roll] |   │
      │ [Start] [Loop]    Time: [50ms] ─━─          │ ← 顶栏
      │                   Amp: [1.0×] ─━─           │
      │                   Speed:[1.0×] ─━─           │
      ├─────────────────────────────────────────────┤
      │ ┌─────────────┐ │ ┌─────────────┐ ┌──────┐ │
      │ │  原始信号    │ │ │  重建信号    │ │ 通道 │ │ ← 波形区
      │ │  (左侧)     │ │ │  (右侧)     │ │ 滑块 │ │
      │ └─────────────┘ │ └─────────────┘ └──────┘ │
      └─────────────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SignalViewer")
        self.resize(1600, 900)

        # ── 核心对象 ─────────────────────────────────────
        self._sd = SignalData()          # 数据容器（原始 + 重建）
        self._player = Player()          # 播放引擎

        # ── 连接播放信号 ─────────────────────────────────
        self._player.frame_ready.connect(self._on_frame)
        self._player.state_changed.connect(self._on_state)

        # ── 状态 ─────────────────────────────────────────
        self._details: weakref.WeakSet = weakref.WeakSet()  # 详情窗弱引用集
        self._loader: LoaderWorker = None                   # 当前异步加载线程
        self._mode = "row"  # 当前显示模式: "row" | "tile" | "scope"

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

        # ── 文件加载按钮 ──────────────────────────────────
        self._btn_orig = QtWidgets.QPushButton("Load Rawdata (.mat)")
        self._btn_orig.clicked.connect(self._load_orig)

        self._btn_recon = QtWidgets.QPushButton("Load Recdata (.mat)")
        self._btn_recon.clicked.connect(self._load_recon)
        self._btn_recon.setEnabled(False)  # 先加载原始信号后才能加载重建

        bar.addWidget(self._btn_orig)
        bar.addWidget(self._btn_recon)
        bar.addWidget(self._make_vsep())

        # ── 模式切换按钮（三段式）─────────────────────────
        # 无专属样式，完全继承 config.py 全局按钮风格
        self._btn_row = QtWidgets.QPushButton("Compare")
        self._btn_row.setCheckable(True)
        self._btn_row.setChecked(True)

        self._btn_tile = QtWidgets.QPushButton("Browse")
        self._btn_tile.setCheckable(True)

        self._btn_scope = QtWidgets.QPushButton("Roll")
        self._btn_scope.setCheckable(True)

        # QButtonGroup 保证三者互斥（同一时间只有一个 checked）
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

        root.addLayout(bar)

        # ══ 分隔线 ════════════════════════════════════════
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ══ 波形显示区 ════════════════════════════════════
        wave_row = QtWidgets.QHBoxLayout()
        wave_row.setContentsMargins(0, 4, 8, 4)  # 右侧留 8px 防止滚动条贴墙
        wave_row.setSpacing(4)

        # GridView — 管理 Compare (Row) 和 Browse (Tile) 两种模式
        self._grid = GridView(self._sd)
        self._grid.channel_clicked.connect(self._open_detail)

        # OscilloscopeView — Roll 模式
        self._scope = OscilloscopeView(self._sd)
        self._scope.channel_clicked.connect(self._open_detail)

        # QStackedLayout 叠加两个视图，按模式切换
        self._view_stack = QtWidgets.QStackedLayout()
        self._view_stack.addWidget(self._grid)    # 索引 0
        self._view_stack.addWidget(self._scope)   # 索引 1
        self._view_stack.setCurrentIndex(0)

        wave_row.addLayout(self._view_stack, 1)

        # 右侧通道浏览滑动条
        # 改粗细: setFixedWidth(18 → 更大/更小)
        # 改范围: setMaximum 在 _load_recon 中动态设置
        self._slider_ch = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self._slider_ch.setMinimum(0)
        self._slider_ch.setMaximum(0)              # 加载数据后更新
        self._slider_ch.setInvertedAppearance(True) # 向上拖 = 值增大
        self._slider_ch.setInvertedControls(True)
        self._slider_ch.setFixedWidth(18)           # 滑条宽度（粗细）
        self._slider_ch.valueChanged.connect(self._on_ch_scroll)
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
        f.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
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
        """绑定键盘快捷键 — 仅保留 Space 播放/暂停。"""
        Shortcut = QtWidgets.QShortcut
        QtKey = QtCore.Qt
        KeySeq = QtGui.QKeySequence

        Shortcut(KeySeq(QtKey.Key_Space), self,
                 activated=lambda: self._player.toggle())           # 播放/暂停

    # ═══════════════════════════════════════════════════════════
    # 模式切换
    # ═══════════════════════════════════════════════════════════

    def _on_mode_change(self, btn):
        """模式按钮点击回调。QButtonGroup 保证互斥。"""
        mode_map = {self._btn_row: "row",
                     self._btn_tile: "tile",
                     self._btn_scope: "scope"}
        new_mode = mode_map.get(btn, "row")
        if new_mode == self._mode:
            return
        self._mode = new_mode

        if new_mode == "scope":
            self._view_stack.setCurrentIndex(1)  # 显示 OscilloscopeView
            if self._sd.ready:
                self._scope.set_channel_range(0, 8)
        else:
            self._view_stack.setCurrentIndex(0)  # 显示 GridView
            self._grid.set_mode(new_mode)        # "row" 或 "tile"
            if self._sd.ready:
                self._grid.build()
                self._slider_ch.setMaximum(
                    max(0, self._sd.max_channel_offset))

        self._update_status()

    def _load_orig(self):
        """加载原始信号 .mat 文件。"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Rawdata .mat File", "",
            "MAT Files (*.mat);;All (*)")
        if not path:
            return

        def on_done(data, s_freq, raw_path):
            """加载完成回调（在主线程中执行）。"""
            self._sd.orig = data
            self._sd.orig_path = raw_path or path
            self._sd.s_freq = s_freq
            self._sd.n_chan = data.shape[0]
            self._sd.n_samples = data.shape[1]
            self._btn_recon.setEnabled(True)  # 原始加载完才能加载重建
            self._update_status()

        self._load_mat_async(path, "Loading Rawdata", on_done)

    def _load_recon(self):
        """加载重建信号 .mat 文件。

        校验: 通道数必须匹配原始信号（允许转置修正）。
              时间长度以较短的为准。
        加载完成后: 计算通道参数 → 构建视图 → 启用所有控件。
        """
        if self._sd.orig is None:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Recdata .mat File", "",
            "MAT Files (*.mat);;All (*)")
        if not path:
            return

        def on_done(recon, _s_freq, raw_path):
            try:
                # ── 通道数校验 ──────────────────────────────
                if recon.shape[0] != self._sd.n_chan:
                    if recon.shape[1] == self._sd.n_chan:
                        recon = recon.T  # 自动转置（行/列互换）
                    else:
                        raise ValueError(
                            f"Channel count mismatch! "
                            f"Rawdata: {self._sd.n_chan}, "
                            f"Recdata: {recon.shape[0]}")

                # ── 长度对齐（取较短者）─────────────────────
                min_len = min(self._sd.n_samples, recon.shape[1])
                if self._sd.orig.shape[1] > min_len:
                    self._sd.orig = self._sd.orig[:, :min_len]
                self._sd.recon = recon[:, :min_len]
                self._sd.recon_path = raw_path or path
                self._sd.n_samples = min_len

                # ── 计算每通道幅值 ──────────────────────────
                self._sd.compute_params()

                # ── 构建视图 ────────────────────────────────
                if self._mode == "scope":
                    self._scope.set_channel_range(0, 8)
                else:
                    self._grid.set_mode(self._mode)
                    self._grid.build()

                # ── 配置播放器 ──────────────────────────────
                self._player.configure(
                    self._sd.s_freq, self._sd.n_samples,
                    self._sd.window_pts)
                self._player.seek(0)

                # ── 启用所有控件 ────────────────────────────
                self._slider_ch.setMaximum(
                    max(0, self._sd.max_channel_offset))
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

        self._load_mat_async(path, "Loading Recdata", on_done)

    def _load_mat_async(self, path: str, title: str, on_done):
        """异步加载 .mat 文件。

        显示一个模态进度对话框（不停旋转的进度条），
        LoaderWorker 在后台线程中执行实际加载。
        完成后自动关闭对话框并调用 on_done 回调。
        """
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
        """播放器每帧回调。将当前 ptr 分发给当前显示的视图。

        流程:
          1. Player._tick() → frame_ready(ptr)
          2. _on_frame → grid.scroll(ptr) 或 scope.scroll(ptr)
          3. Player.ack() → 释放 _pending 锁

        finally 块保证 ack() 一定执行：即使视图渲染抛异常，
        _pending 锁也会释放，播放器不会永久冻结。
        """
        if not self._sd.ready:
            return
        try:
            ptr = self._player.ptr
            if ptr + self._sd.window_pts > self._sd.n_samples:
                return
            if self._mode == "scope":
                self._scope.scroll(ptr, self._sd)
            else:
                self._grid.scroll(ptr, self._sd)
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

    def _on_ch_scroll(self, val: int):
        """通道滑动条回调。仅在 Row/Tile 模式生效。"""
        if not self._sd.ready:
            return
        if self._mode != "scope":
            self._grid.set_offset(self._sd, val)

    def _on_win_slider(self, val: int):
        """时窗滑动条: 0-1000 → WINDOW_SEC_MIN ~ WINDOW_SEC_MAX 秒。

        改范围: 修改 config.py 的 WINDOW_SEC_MIN / MAX。
        """
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
        """幅值滑动条: 0-1000 → AMP_SCALE_MIN ~ AMP_SCALE_MAX。

        改范围: 修改 config.py 的 AMP_SCALE_MIN / MAX。
        """
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
        dw.move(self.x() + 30, self.y() + 30)             # 稍微偏移
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

    # ═══════════════════════════════════════════════════════════
    # 状态（状态栏已移除，保留空方法防止调用报错）
    # ═══════════════════════════════════════════════════════════

    def _update_status(self):
        pass  # 状态栏已移除
