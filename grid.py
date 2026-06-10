"""
grid.py — 网格视图（核心渲染模块）

  这是整个项目最复杂、最关键的模块。负责将 2048 通道的神经信号
  高效渲染到屏幕上。

  核心设计:
    1. 对象池 (Object Pool)    — 只创建 VISIBLE_ROWS 条曲线，滚动时复用
    2. 窗口裁剪 (Window Clipping)— 每条曲线只存 window_pts(~1500) 个点
    3. 视口剔除 (Viewport Culling)— 只渲染看得见的通道
    4. 零基线 (Zero Baseline)   — 每个通道画虚线参考线
    5. 斑马纹 (Zebra Striping)  — 交替行背景防止串行

  Row 模式 (Compare): VISIBLE_ROWS 条曲线/侧，一通道一行，垂直堆叠
  Tile 模式 (Browse): VISIBLE_TILE_ROWS × TILE_COLS 个栅格/侧

  调参入口:
    config.VISIBLE_ROWS       — Row 模式可见通道数（低配机 4~6）
    config.VISIBLE_TILE_ROWS  — Tile 模式可见行数
    config.TILE_COLS          — Tile 模式每行格子数
    config.LINE_WIDTH         — 波形线宽
    config.SPACING_FACTOR     — 通道间距系数（影响 Y 偏移）
    MAX_POINTS_PER_CURVE      — 每曲线最大点数（超此则步进取样）
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from config import (COLOR_BG, COLOR_CARD, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_SEP, COLOR_ZEBRA, TILE_COLS,
                     VISIBLE_ROWS, VISIBLE_TILE_ROWS, LINE_WIDTH,
                     SPACING_FACTOR)
from data import SignalData
from utils import make_font, make_pen, format_channel_label

# 每曲线最大数据点数。超过此数 → 每隔 N 个取 1 个（简单步进降采样）
# 默认 200ms × 30kHz = 6000 点。一般 window_pts = 1500，远低于上限。
MAX_POINTS_PER_CURVE = 6000


class GridView(QtWidgets.QWidget):
    """网格视图 — 窗口裁剪 + 对象池 + 零线 + 斑马纹。

    信号:
        channel_clicked(int) — 用户点击某通道，发射绝对通道索引
        wheel_time(int)      — 滚轮滚动，+1=放大 -1=缩小时窗
        wheel_amp(int)       — Shift+滚轮，+1=拉大 -1=缩小幅值

    内部模式:
        "row"  — 一行一通道（Compare 按钮）
        "tile" — 栅格模式（Browse 按钮）
    """

    # Qt 信号
    channel_clicked = QtCore.pyqtSignal(int)
    wheel_time = QtCore.pyqtSignal(int)
    wheel_amp = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd                      # 数据容器引用
        self._mode = "row"                 # 当前模式

        # ── Y 轴偏移（8KB，存所有 2048 通道的 Y 中心位置）──
        self._y_offsets: np.ndarray = None
        self._total_height: float = 0.0    # 所有通道堆叠的总高度

        # ── 视口状态 ──────────────────────────────────────
        self._ch_offset: int = 0           # 当前可见的第一个通道索引
        self._last_ptr: int = -1           # 上次渲染的 ptr（去重用）

        # ── 对象池（只存 VISIBLE_ROWS 个对象，不是 2048 个）─
        self._curves_orig: list[pg.PlotDataItem] = []   # 左侧原始信号曲线
        self._curves_recon: list[pg.PlotDataItem] = []  # 右侧重建信号曲线
        self._labels_l: list[pg.TextItem] = []           # 左侧通道标签
        self._labels_r: list[pg.TextItem] = []           # 右侧通道标签
        self._zero_lines_l: list[pg.InfiniteLine] = []   # 左侧零基线
        self._zero_lines_r: list[pg.InfiniteLine] = []   # 右侧零基线
        self._zebra_rects: list[pg.LinearRegionItem] = [] # 斑马纹交替行

        # ── Tile 模式专用 ─────────────────────────────────
        self._tiles_orig: dict[tuple, tuple] = {}  # (row,col) → (PlotItem, curve)
        self._tiles_recon: dict[tuple, tuple] = {}

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    # UI 框架 — 只执行一次
    #     QStackedLayout 叠加 Row 面板和 Tile 面板
    #     根据 mode 切换显示哪一个
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        """构建双层 UI：Row 面板（索引 0）+ Tile 面板（索引 1）。"""
        root = QtWidgets.QStackedLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Row 模式面板 ─────────────────────────────────
        self._row_widget = QtWidgets.QWidget()
        self._row_widget.setStyleSheet(f"background-color: {COLOR_CARD};")
        row_lay = QtWidgets.QHBoxLayout(self._row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(0)

        # 左侧 PlotWidget — 原始信号
        self._left_pw = pg.PlotWidget(background=COLOR_CARD)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        # 中间分隔线
        self._sep_v = self._make_vsep()
        self._sep_v.setStyleSheet(
            f"border: none; background-color: {COLOR_SEP};")

        # 右侧 PlotWidget — 重建信号
        self._right_pw = pg.PlotWidget(background=COLOR_CARD)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        # 左右 Y 轴同步
        self._left_vb.sigYRangeChanged.connect(self._sync_y_range)

        row_lay.addWidget(self._left_pw, 1)
        row_lay.addWidget(self._sep_v)
        row_lay.addWidget(self._right_pw, 1)

        # ── Tile 模式面板 ─────────────────────────────────
        self._tile_widget = QtWidgets.QWidget()
        self._tile_widget.setStyleSheet(f"background-color: {COLOR_CARD};")
        tile_lay = QtWidgets.QHBoxLayout(self._tile_widget)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_lay.setSpacing(0)

        # 左侧栅格 — 原始信号
        self._tile_left = pg.GraphicsLayoutWidget()
        self._tile_left.setBackground(COLOR_CARD)
        # 右侧栅格 — 重建信号
        self._tile_right = pg.GraphicsLayoutWidget()
        self._tile_right.setBackground(COLOR_CARD)

        tile_lay.addWidget(self._tile_left, 1)
        tile_lay.addWidget(self._make_vsep())
        tile_lay.addWidget(self._tile_right, 1)

        root.addWidget(self._row_widget)
        root.addWidget(self._tile_widget)

        # 事件过滤 — 捕获点击（打开 Detail）和滚轮（时窗/幅值）
        self._left_pw.viewport().installEventFilter(self)
        self._right_pw.viewport().installEventFilter(self)
        self._left_pw.scene().installEventFilter(self)
        self._right_pw.scene().installEventFilter(self)

    @staticmethod
    def _make_vsep():
        """创建垂直分隔线。"""
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        f.setFixedWidth(2)
        return f

    def _config_plot(self, pi: pg.PlotItem):
        """配置 PlotItem：隐藏所有装饰，只显示波形和数据。"""
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.hideAxis('bottom')

    # ═══════════════════════════════════════════════════════════
    # 模式切换
    # ═══════════════════════════════════════════════════════════

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """切换 "row" ↔ "tile" 模式。重建曲线池并渲染。"""
        if mode == self._mode:
            return
        self._mode = mode
        self.clear()
        stack: QtWidgets.QStackedLayout = self.layout()
        stack.setCurrentIndex(0 if mode == "row" else 1)
        self._ch_offset = 0
        self._last_ptr = -1
        if self._sd.ready:
            self.build()
            self.set_offset(self._sd, 0)

    # ═══════════════════════════════════════════════════════════
    # 构建 — 创建对象池，仅 VISIBLE_ROWS 个曲线
    # ═══════════════════════════════════════════════════════════

    def build(self):
        """(重)构建整个视图。"""
        self.clear()
        sd = self._sd
        if not sd.ready:
            return

        # 计算全量 Y 偏移（8KB，可忽略）
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)
        self._ch_offset = 0
        self._last_ptr = -1

        if self._mode == "row":
            self._build_row_pool(sd)
        else:
            self._build_tile_pool(sd)

    def _build_row_pool(self, sd: SignalData):
        """Row 模式对象池: VISIBLE_ROWS 条曲线 + 零线 + 斑马纹 + 左右标签。

        关键: 只创建 VISIBLE_ROWS 条曲线（不是 2048 条）。
              滚动时通过 _fill_row_data 换绑数据，不创建新对象。
        """
        n_pool = min(VISIBLE_ROWS, sd.n_chan)
        w = sd.window_sec
        row_h = self._total_height / max(1, sd.n_chan)  # 每行高度

        # ── 斑马纹 — 偶数行加浅色背景 ────────────────────
        for i in range(n_pool):
            if i % 2 == 1:
                continue  # 只给偶数行加斑马纹
            abs_ch = i
            offset = float(self._y_offsets[abs_ch])
            zebra = pg.LinearRegionItem(
                values=[offset - row_h / 2, offset + row_h / 2],
                orientation='horizontal',
                brush=pg.mkBrush(COLOR_ZEBRA),
                pen=pg.mkPen(None))           # 无边框
            zebra.setMovable(False)           # 用户不可拖动
            self._left_pi.addItem(zebra)
            self._zebra_rects.append(zebra)

        # ── 曲线 + 零线 + 标签 ────────────────────────────
        for i in range(n_pool):
            abs_ch = i
            offset = float(self._y_offsets[abs_ch])

            # 零基线（虚线）
            dash_pen = pg.mkPen(color=COLOR_GRID, width=0.5,
                                style=QtCore.Qt.DashLine)
            zl = pg.InfiniteLine(pos=offset, angle=0, pen=dash_pen)
            zr = pg.InfiniteLine(pos=offset, angle=0, pen=dash_pen)
            self._left_pi.addItem(zl)
            self._right_pi.addItem(zr)
            self._zero_lines_l.append(zl)
            self._zero_lines_r.append(zr)

            # 信号曲线
            c_l = self._left_pi.plot(pen=make_pen(COLOR_ORIG, LINE_WIDTH))
            c_l.setDownsampling(auto=False)    # 手动控制降采样
            c_l.setSkipFiniteCheck(True)       # 跳过 NaN/Inf 检查（性能优化）
            self._curves_orig.append(c_l)

            c_r = self._right_pi.plot(pen=make_pen(COLOR_RECON, LINE_WIDTH))
            c_r.setDownsampling(auto=False)
            c_r.setSkipFiniteCheck(True)
            self._curves_recon.append(c_r)

            # 左侧标签
            lbl_l = pg.TextItem("", color=COLOR_TEXT, anchor=(0, 0.5))
            lbl_l.setFont(make_font(8))
            self._left_pi.addItem(lbl_l)
            self._labels_l.append(lbl_l)

            # 右侧标签
            lbl_r = pg.TextItem("", color=COLOR_TEXT, anchor=(1, 0.5))
            lbl_r.setFont(make_font(8))
            self._right_pi.addItem(lbl_r)
            self._labels_r.append(lbl_r)

        # 填充初始数据
        self._fill_row_data(sd, 0)

        # 设置视口范围
        self._left_vb.setXRange(0, w, padding=0)
        self._right_vb.setXRange(0, w, padding=0)

        self._left_vb.setYRange(
            max(0, self._total_height - n_pool * row_h),
            self._total_height, padding=0)
        self._right_vb.setYRange(
            max(0, self._total_height - n_pool * row_h),
            self._total_height, padding=0)

    def _build_tile_pool(self, sd: SignalData):
        """Tile 模式: 创建栅格网格。

        每个 tile 是一个独立的 PlotItem（含零线）。
        GraphicsLayoutWidget 自动管理行列布局。
        """
        n_rows = min(VISIBLE_TILE_ROWS,
                     (sd.n_chan + TILE_COLS - 1) // TILE_COLS)
        w = sd.window_sec
        font = make_font(7)

        for r in range(n_rows):
            for c in range(TILE_COLS):
                abs_ch = r * TILE_COLS + c
                if abs_ch >= sd.n_chan:
                    break
                ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
                y_lo, y_hi = -ch_amp * 1.2, ch_amp * 1.2  # Y 范围: ±幅值×1.2

                # 左侧 tile
                pi_l = self._tile_left.addPlot(row=r, col=c)
                self._config_tile_plot(pi_l, abs_ch, font, y_lo, y_hi)
                _add_tile_zero_line(pi_l, y_lo, y_hi)
                c_l = pi_l.plot(pen=make_pen(COLOR_ORIG, 0.4))
                c_l.setDownsampling(auto=False)
                c_l.setSkipFiniteCheck(True)
                self._tiles_orig[(r, c)] = (pi_l, c_l)

                # 右侧 tile
                pi_r = self._tile_right.addPlot(row=r, col=c)
                self._config_tile_plot(pi_r, abs_ch, font, y_lo, y_hi)
                _add_tile_zero_line(pi_r, y_lo, y_hi)
                c_r = pi_r.plot(pen=make_pen(COLOR_RECON, 0.4))
                c_r.setDownsampling(auto=False)
                c_r.setSkipFiniteCheck(True)
                self._tiles_recon[(r, c)] = (pi_r, c_r)

        self._fill_tile_data(sd, 0)

        for pi, _ in list(self._tiles_orig.values()):
            pi.setXRange(0, w, padding=0)
        for pi, _ in list(self._tiles_recon.values()):
            pi.setXRange(0, w, padding=0)

    def _config_tile_plot(self, pi: pg.PlotItem, ch: int,
                          font: QtGui.QFont, y_lo: float, y_hi: float):
        """配置单个 Tile 的 PlotItem。"""
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.hideAxis('bottom')
        pi.setYRange(y_lo, y_hi, padding=0)
        label = pg.TextItem(format_channel_label(ch),
                            color=COLOR_TEXT, anchor=(0, 0.5))
        label.setFont(font)
        pi.addItem(label)
        label.setPos(0, 0)

    def clear(self):
        """清空所有曲线、标签、零线、斑马纹、tile。

        在模式切换和 rebuild 时调用。
        """
        self._left_pi.clear()
        self._right_pi.clear()
        self._tile_left.clear()
        self._tile_right.clear()
        self._curves_orig.clear()
        self._curves_recon.clear()
        self._labels_l.clear()
        self._labels_r.clear()
        self._zero_lines_l.clear()
        self._zero_lines_r.clear()
        self._zebra_rects.clear()
        self._tiles_orig.clear()
        self._tiles_recon.clear()

    # ═══════════════════════════════════════════════════════════
    # 数据填充 — 热路径，每次滚动/每帧播放都调用
    #    从 memmap 读取当前窗口数据 → setData 到曲线
    #    同时更新零线位置、标签位置、斑马纹位置
    # ═══════════════════════════════════════════════════════════

    def _fill_row_data(self, sd: SignalData, ptr: int):
        """Row 模式核心渲染: 从 memmap 读取可见通道的当前窗口数据。

        Args:
            sd:  数据容器
            ptr: 当前播放位置（采样点索引）

        性能: 16 条曲线 × 1500 点 = 24k floats ≈ 96KB。极轻量。
        """
        wp = sd.window_pts               # 窗口采样点数 (~1500)
        if ptr + wp > sd.n_samples:      # 边界保护
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)   # memmap 切片（不复制数据）
        t = np.arange(wp, dtype=np.float32) / sd.s_freq  # 时间轴
        t, wp = _clip_to_screen(t, wp)   # 超限时步进降采样

        n_pool = len(self._curves_orig)
        row_h = self._total_height / max(1, sd.n_chan)

        for i in range(n_pool):
            abs_ch = self._ch_offset + i  # 绝对通道索引
            active = abs_ch < sd.n_chan

            if active:
                offset = float(self._y_offsets[abs_ch])
                # 从 memmap 读当前通道 + 当前窗口的数据
                self._curves_orig[i].setData(
                    t, sd.orig[abs_ch, t_slice][:wp] + offset)
                self._curves_recon[i].setData(
                    t, sd.recon[abs_ch, t_slice][:wp] + offset)
            else:
                offset = 0.0

            vis = active
            self._curves_orig[i].setVisible(vis)
            self._curves_recon[i].setVisible(vis)

            # 更新零线位置
            if i < len(self._zero_lines_l):
                self._zero_lines_l[i].setPos(offset)
                self._zero_lines_l[i].setVisible(vis)
            if i < len(self._zero_lines_r):
                self._zero_lines_r[i].setPos(offset)
                self._zero_lines_r[i].setVisible(vis)

            # 更新标签
            lbl_text = format_channel_label(abs_ch) if active else ""
            if i < len(self._labels_l):
                self._labels_l[i].setText(lbl_text)
                self._labels_l[i].setPos(0.0005, offset)
            if i < len(self._labels_r):
                self._labels_r[i].setText(lbl_text)
                self._labels_r[i].setPos(sd.window_sec - 0.0005, offset)

            # 更新斑马纹（仅偶数行）
            zi = i // 2
            if i % 2 == 0 and zi < len(self._zebra_rects):
                if active:
                    rgn = self._zebra_rects[zi]
                    rgn.setRegion([offset - row_h / 2, offset + row_h / 2])
                    rgn.setVisible(True)
                else:
                    self._zebra_rects[zi].setVisible(False)

    def _fill_tile_data(self, sd: SignalData, ptr: int):
        """Tile 模式核心渲染: 更新所有可见栅格的数据。"""
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        t = np.arange(wp, dtype=np.float32) / sd.s_freq
        t, wp = _clip_to_screen(t, wp)

        # 更新左侧栅格
        for (r, c), (pi, curve) in list(self._tiles_orig.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch >= sd.n_chan:
                continue
            ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
            pi.setYRange(-ch_amp * 1.2, ch_amp * 1.2, padding=0)
            curve.setData(t, sd.orig[abs_ch, t_slice][:wp])
            _update_tile_label(pi, abs_ch)

        # 更新右侧栅格
        for (r, c), (pi, curve) in list(self._tiles_recon.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch >= sd.n_chan:
                continue
            ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
            pi.setYRange(-ch_amp * 1.2, ch_amp * 1.2, padding=0)
            curve.setData(t, sd.recon[abs_ch, t_slice][:wp])

    # ═══════════════════════════════════════════════════════════
    # 视口同步 — 左右 ViewBox Y 轴联动
    # ═══════════════════════════════════════════════════════════

    def _sync_y_range(self, vb, range_):
        """左侧 Y 范围变化 → 同步到右侧。blockSignals 防止递归。"""
        try:
            self._right_vb.blockSignals(True)
            self._right_vb.setYRange(*range_, padding=0)
        finally:
            self._right_vb.blockSignals(False)

    # ═══════════════════════════════════════════════════════════
    # 外部接口（由 app.py 调用）
    # ═══════════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        """播放时每帧调用。更新可见通道的窗口数据。

        ptr 去重优化: 如果 ptr 没变就跳过（避免重复渲染同一帧）。
        """
        if ptr == self._last_ptr:
            return
        self._last_ptr = ptr

        if self._mode == "row":
            self._fill_row_data(sd, ptr)
        else:
            self._fill_tile_data(sd, ptr)

    def set_offset(self, sd: SignalData, val: int):
        """通道滑动条回调。更新可见通道范围 + Y 视口。

        Args:
            val: 滑动条值（第一个可见通道的索引）
        """
        if not sd.ready:
            return
        val = max(0, min(val, sd.max_channel_offset))
        if val == self._ch_offset:
            return  # 无变化，跳过
        self._ch_offset = val

        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            n_pool = len(self._curves_orig)
            row_h = self._total_height / max(1, sd.n_chan)
            y_top = self._total_height - self._ch_offset * row_h
            y_bot = max(0, y_top - n_pool * row_h)
            self._left_vb.setYRange(y_bot, y_top, padding=0)
            self._right_vb.setYRange(y_bot, y_top, padding=0)
        else:
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def update_ranges(self, sd: SignalData):
        """时窗变化回调。更新 X 范围 + 重填数据。"""
        w = sd.window_sec
        if self._mode == "row":
            self._left_vb.setXRange(0, w, padding=0)
            self._right_vb.setXRange(0, w, padding=0)
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
        else:
            for pi, _ in list(self._tiles_orig.values()):
                pi.setXRange(0, w, padding=0)
            for pi, _ in list(self._tiles_recon.values()):
                pi.setXRange(0, w, padding=0)
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def reload_amp(self, sd: SignalData):
        """幅值变化回调。重算 Y 偏移 + 更新数据 + Y 视口。"""
        if not sd.ready:
            return
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)

        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            n_pool = len(self._curves_orig)
            row_h = self._total_height / max(1, sd.n_chan)
            y_top = self._total_height - self._ch_offset * row_h
            y_bot = max(0, y_top - n_pool * row_h)
            self._left_vb.setYRange(y_bot, y_top, padding=0)
            self._right_vb.setYRange(y_bot, y_top, padding=0)
        else:
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    # ═══════════════════════════════════════════════════════════
    # 事件过滤 — 滚轮（时窗/幅值）+ 点击（打开 Detail）
    # ═══════════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        if not self._sd.ready or self._y_offsets is None:
            return False

        # 滚轮 → 时窗（普通）或幅值（Shift+滚轮）
        if event.type() == QtCore.QEvent.Wheel:
            delta = 1 if event.angleDelta().y() > 0 else -1
            modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
            if modifiers & QtCore.Qt.ShiftModifier:
                self.wheel_amp.emit(delta)
            else:
                self.wheel_time.emit(delta)
            return False

        # 左键点击 → 确定通道 → 发射 channel_clicked
        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):
            if self._mode == "row":
                # 确定点击来源（左侧或右侧 ViewBox）
                pw = self._left_pw if obj in (
                    self._left_pw.viewport(),
                    self._left_pw.scene()) else self._right_pw
                vb = pw.getPlotItem().getViewBox()
                data_pt = vb.mapToView(pg.Point(event.pos()))
                y = float(data_pt.y())
                # 找 Y 坐标最接近的通道
                ch = int(np.argmin(np.abs(self._y_offsets - y)))
                if 0 <= ch < self._sd.n_chan:
                    self.channel_clicked.emit(ch)
                return True

        return False


# ═══════════════════════════════════════════════════════════════
# 模块级工具函数
# ═══════════════════════════════════════════════════════════════

def _clip_to_screen(t: np.ndarray, wp: int) -> tuple[np.ndarray, int]:
    """简单步进降采样。当数据点数超过 MAX_POINTS_PER_CURVE 时，每隔 N 个取 1 个。

    Args:
        t:  时间轴数组
        wp: 原始数据点数

    Returns:
        (裁剪后的 t, 裁剪后的 wp)

    注意: 正常情况 window_pts ≈ 1500 < MAX_POINTS_PER_CURVE(6000)，
          所以这个函数通常不做任何裁剪，直接返回原值。
    """
    if wp > MAX_POINTS_PER_CURVE:
        step = wp // MAX_POINTS_PER_CURVE + 1
        return t[::step], len(t[::step])
    return t, wp


def _update_tile_label(pi: pg.PlotItem, ch: int):
    """更新 Tile 的通道标签文本（用于滚动时换绑通道）。"""
    for item in pi.items:
        if isinstance(item, pg.TextItem):
            item.setText(format_channel_label(ch))
            break


def _add_tile_zero_line(pi: pg.PlotItem, y_lo: float, y_hi: float):
    """在 Tile 的 PlotItem 中添加 Y=0 的虚线参考线。"""
    line = pg.InfiniteLine(pos=0, angle=0,
                            pen=pg.mkPen(color=COLOR_GRID, width=0.5,
                                         style=QtCore.Qt.DashLine))
    pi.addItem(line)
