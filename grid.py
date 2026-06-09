"""
grid.py — 网格视图

  GridView  : Row 模式 + Tile 模式，分块渲染，视口剔除
              左侧 = 原始信号，右侧 = 重建信号

  Row 模式: 一个通道一行，左右 ViewBox 同步
  Tile 模式: 6 通道/行，各自独立小栅格

  信号:
    channel_clicked(int) — 点击了某个通道（绝对索引）
    wheel_time(int)      — +1 放大时窗, -1 缩小
    wheel_amp(int)       — +1 拉大幅值, -1 缩小
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from config import (COLOR_BG, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_SEP, TILE_COLS, VISIBLE_ROWS,
                     VISIBLE_TILE_ROWS, LINE_WIDTH, SPACING_FACTOR,
                     DECIMATION_TARGET, MINMAX_BUCKETS)
from data import SignalData
from decimator import lttb, minmax
from utils import make_font, make_pen, format_channel_label


class GridView(QtWidgets.QWidget):
    """网格视图 — 支持 Row 和 Tile 两种显示模式。

    Row 模式: 左侧 ViewBox (原始) + 右侧 ViewBox (重建)，通道垂直堆叠。
    Tile 模式: 左侧栅格 (原始) + 右侧栅格 (重建)，6 列。
    """

    channel_clicked = QtCore.pyqtSignal(int)
    wheel_time = QtCore.pyqtSignal(int)
    wheel_amp = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd
        self._mode = "row"          # "row" | "tile"
        self._y_offsets: np.ndarray = None
        self._total_height: float = 0.0
        self._visible_start: int = 0   # 当前可见起始通道 (行索引)
        self._t_buf = np.empty(0, dtype=np.float32)

        # 曲线缓存: key=ch, value=PlotDataItem
        self._curves_orig: dict[int, pg.PlotDataItem] = {}
        self._curves_recon: dict[int, pg.PlotDataItem] = {}
        # 标签缓存
        self._labels: dict[int, pg.TextItem] = {}
        # Tile 模式: (row, col) → (PlotItem, curve)
        self._tiles_orig: dict[tuple, tuple] = {}
        self._tiles_recon: dict[tuple, tuple] = {}

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        """构建双层布局：row_layout 和 tile_layout 叠加，按模式切换可见。"""
        root = QtWidgets.QStackedLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Row 模式容器 ──────────────────────────────────
        self._row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self._row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # 左侧 ViewBox — 原始信号
        self._left_pw = pg.PlotWidget(background=COLOR_BG)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        # 右侧 ViewBox — 重建信号
        self._right_pw = pg.PlotWidget(background=COLOR_BG)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        # 同步 Y 轴
        self._left_vb.sigYRangeChanged.connect(self._sync_y_range)

        row_layout.addWidget(self._left_pw, 1)
        # 中间分隔
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        sep.setFixedWidth(1)
        row_layout.addWidget(sep)
        row_layout.addWidget(self._right_pw, 1)

        # ── Tile 模式容器 ─────────────────────────────────
        self._tile_widget = QtWidgets.QWidget()
        tile_layout = QtWidgets.QHBoxLayout(self._tile_widget)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.setSpacing(0)

        self._tile_left = pg.GraphicsLayoutWidget()
        self._tile_left.setBackground(COLOR_BG)
        self._tile_right = pg.GraphicsLayoutWidget()
        self._tile_right.setBackground(COLOR_BG)
        tile_layout.addWidget(self._tile_left, 1)

        sep2 = QtWidgets.QFrame()
        sep2.setFrameShape(QtWidgets.QFrame.VLine)
        sep2.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        sep2.setFixedWidth(1)
        tile_layout.addWidget(sep2)
        tile_layout.addWidget(self._tile_right, 1)

        root.addWidget(self._row_widget)
        root.addWidget(self._tile_widget)

        # ── 事件过滤 ──────────────────────────────────────
        self._left_pw.viewport().installEventFilter(self)
        self._right_pw.viewport().installEventFilter(self)
        self._left_pw.scene().installEventFilter(self)
        self._right_pw.scene().installEventFilter(self)

    def _config_plot(self, pi: pg.PlotItem):
        """配置 PlotItem 通用属性。"""
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
        """切换显示模式: "row" | "tile" """
        if mode == self._mode:
            return
        self._mode = mode
        self.clear()
        stack: QtWidgets.QStackedLayout = self.layout()
        if mode == "row":
            stack.setCurrentIndex(0)
        else:
            stack.setCurrentIndex(1)
        if self._sd.ready:
            self.build()
            self._render_visible()

    # ═══════════════════════════════════════════════════════════
    # 构建 / 清理
    # ═══════════════════════════════════════════════════════════

    def build(self):
        """(重)构建所有曲线对象。"""
        self.clear()
        sd = self._sd
        if not sd.ready:
            return

        if self._mode == "row":
            self._build_row()
        else:
            self._build_tile()

    def _build_row(self):
        """Row 模式：为所有通道创建曲线（左右各一），设置 Y 偏移。"""
        sd = self._sd
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)

        font = make_font(8)

        for ch in range(sd.n_chan):
            offset = float(self._y_offsets[ch])

            # 左侧 — 原始信号
            c_orig = self._left_pi.plot(
                pen=make_pen(COLOR_ORIG, LINE_WIDTH))
            c_orig.setDownsampling(auto=False)
            c_orig.setSkipFiniteCheck(True)
            self._curves_orig[ch] = c_orig

            # 右侧 — 重建信号
            c_recon = self._right_pi.plot(
                pen=make_pen(COLOR_RECON, LINE_WIDTH))
            c_recon.setDownsampling(auto=False)
            c_recon.setSkipFiniteCheck(True)
            self._curves_recon[ch] = c_recon

            # 通道标签（仅左侧）
            lbl = pg.TextItem(format_channel_label(ch),
                              color=COLOR_TEXT, anchor=(0, 0.5))
            lbl.setFont(font)
            self._left_pi.addItem(lbl)
            lbl.setPos(0.0005, offset)
            self._labels[ch] = lbl

        # 初始数据加载
        self._load_all_row_data(sd)

        # X/Y 范围
        w = sd.window_sec
        self._left_vb.setXRange(0, w, padding=0)
        self._right_vb.setXRange(0, w, padding=0)

        n_show = min(VISIBLE_ROWS, sd.n_chan)
        row_h = self._total_height / max(1, sd.n_chan)
        self._left_vb.setYRange(
            self._total_height - n_show * row_h, self._total_height, padding=0)
        self._right_vb.setYRange(
            self._total_height - n_show * row_h, self._total_height, padding=0)

    def _load_all_row_data(self, sd: SignalData):
        """Row 模式：全量数据写入曲线（首次构建 / 幅值变化时）。"""
        if not sd.ready:
            return
        t = np.arange(sd.n_samples, dtype=np.float32) / sd.s_freq
        for ch in range(sd.n_chan):
            offset = float(self._y_offsets[ch])
            if ch in self._curves_orig:
                self._curves_orig[ch].setData(
                    t, sd.orig[ch, :] + offset)
            if ch in self._curves_recon:
                self._curves_recon[ch].setData(
                    t, sd.recon[ch, :] + offset)

    def _build_tile(self):
        """Tile 模式：创建 TILE_COLS × N 栅格网格。"""
        sd = self._sd
        n_rows = (sd.n_chan + TILE_COLS - 1) // TILE_COLS

        for side, glw, curves_dict, tiles_dict in [
            ("orig", self._tile_left, self._curves_orig, self._tiles_orig),
            ("recon", self._tile_right, self._curves_recon, self._tiles_recon)
        ]:
            glw.clear()
            curves_dict.clear()
            tiles_dict.clear()

        self._y_offsets = sd.y_offsets_all()
        labels_font = make_font(7)

        for ch in range(sd.n_chan):
            row = ch // TILE_COLS
            col = ch % TILE_COLS

            # 左侧 tile
            pi_l = self._tile_left.addPlot(row=row, col=col)
            self._config_tile_plot(pi_l, ch, labels_font)
            c_l = pi_l.plot(pen=make_pen(COLOR_ORIG, 0.4))
            c_l.setDownsampling(auto=False)
            c_l.setSkipFiniteCheck(True)
            self._tiles_orig[(row, col)] = (pi_l, c_l)
            self._curves_orig[ch] = c_l

            # 右侧 tile
            pi_r = self._tile_right.addPlot(row=row, col=col)
            self._config_tile_plot(pi_r, ch, labels_font)
            c_r = pi_r.plot(pen=make_pen(COLOR_RECON, 0.4))
            c_r.setDownsampling(auto=False)
            c_r.setSkipFiniteCheck(True)
            self._tiles_recon[(row, col)] = (pi_r, c_r)
            self._curves_recon[ch] = c_r

        # 加载数据
        self._load_all_tile_data(sd)

    def _config_tile_plot(self, pi: pg.PlotItem, ch: int, font: QtGui.QFont):
        """配置 Tile 中的单个小 PlotItem。"""
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.hideAxis('bottom')
        label = pg.TextItem(format_channel_label(ch),
                            color=COLOR_TEXT, anchor=(0, 0.5))
        label.setFont(font)
        pi.addItem(label)
        label.setPos(0, 0)

    def _load_all_tile_data(self, sd: SignalData):
        """Tile 模式：全量数据写入所有栅格曲线。"""
        if not sd.ready:
            return
        t = np.arange(sd.n_samples, dtype=np.float32) / sd.s_freq
        for ch in range(sd.n_chan):
            if ch in self._curves_orig:
                self._curves_orig[ch].setData(t, sd.orig[ch, :])
            if ch in self._curves_recon:
                self._curves_recon[ch].setData(t, sd.recon[ch, :])

    def clear(self):
        """清理所有曲线和标签。"""
        self._left_pi.clear()
        self._right_pi.clear()
        self._tile_left.clear()
        self._tile_right.clear()
        self._curves_orig.clear()
        self._curves_recon.clear()
        self._labels.clear()
        self._tiles_orig.clear()
        self._tiles_recon.clear()

    # ═══════════════════════════════════════════════════════════
    # 视口同步
    # ═══════════════════════════════════════════════════════════

    def _sync_y_range(self, vb, range_):
        """左侧 Y 变化 → 同步右侧。"""
        try:
            self._right_vb.blockSignals(True)
            self._right_vb.setYRange(*range_, padding=0)
        finally:
            self._right_vb.blockSignals(False)

    # ═══════════════════════════════════════════════════════════
    # 播放滚动
    # ═══════════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        """播放时平移 X 视口（热路径，零分配）。"""
        t0 = ptr / sd.s_freq
        w = sd.window_sec
        if self._mode == "row":
            self._left_vb.setXRange(t0, t0 + w, padding=0)
            self._right_vb.setXRange(t0, t0 + w, padding=0)
        else:
            # Tile 模式：更新所有可见 tile 的 X 范围
            self._update_tile_x_ranges(t0, w)

    def _update_tile_x_ranges(self, t0: float, w: float):
        """Tile 模式更新 X 范围（所有 tile）。"""
        for pi, _ in self._tiles_orig.values():
            pi.setXRange(t0, t0 + w, padding=0)
        for pi, _ in self._tiles_recon.values():
            pi.setXRange(t0, t0 + w, padding=0)

    # ═══════════════════════════════════════════════════════════
    # 通道滚动
    # ═══════════════════════════════════════════════════════════

    def set_offset(self, sd: SignalData, val: int):
        """竖向浏览：调整 Y 视口到目标行。"""
        self._visible_start = val
        if not sd.ready:
            return

        if self._mode == "row":
            n_total = max(1, sd.n_chan)
            n_visible = min(VISIBLE_ROWS, n_total)
            row_h = self._total_height / n_total
            bot = self._total_height - (val + n_visible) * row_h
            top = self._total_height - val * row_h
            bot = max(0, bot)
            self._left_vb.setYRange(bot, top, padding=0)
            self._right_vb.setYRange(bot, top, padding=0)

    # ═══════════════════════════════════════════════════════════
    # 范围更新
    # ═══════════════════════════════════════════════════════════

    def update_ranges(self, sd: SignalData):
        """时窗变化时更新 X 范围。"""
        w = sd.window_sec
        if self._mode == "row":
            self._left_vb.setXRange(0, w, padding=0)
            self._right_vb.setXRange(0, w, padding=0)
        else:
            self._update_tile_x_ranges(0, w)

    def reload_amp(self, sd: SignalData, data_orig: np.ndarray,
                   data_recon: np.ndarray):
        """幅值变化：重建 Y 偏移 + 重写曲线数据。"""
        if not sd.ready:
            return
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)

        if self._mode == "row":
            self._load_all_row_data(sd)
            n_show = min(VISIBLE_ROWS, max(1, sd.n_chan))
            row_h = self._total_height / max(1, sd.n_chan)
            self._left_vb.setYRange(
                self._total_height - n_show * row_h,
                self._total_height, padding=0)
            self._right_vb.setYRange(
                self._total_height - n_show * row_h,
                self._total_height, padding=0)
            # 更新标签位置
            for ch in range(sd.n_chan):
                if ch in self._labels:
                    self._labels[ch].setPos(
                        0.0005, float(self._y_offsets[ch]))
        else:
            self._load_all_tile_data(sd)

    # ═══════════════════════════════════════════════════════════
    # 渲染可见通道（视口剔除）
    # ═══════════════════════════════════════════════════════════

    def _render_visible(self):
        """仅渲染视口内可见的通道。用于初始加载后和滚动时调用。"""
        pass  # Row 模式: 全量数据已 setData, 播放仅平移 ViewBox, 零重绘

    # ═══════════════════════════════════════════════════════════
    # 事件过滤
    # ═══════════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        if not self._sd.ready or self._y_offsets is None:
            return False

        # 滚轮 → 时窗 / 幅值
        if event.type() == QtCore.QEvent.Wheel:
            delta = 1 if event.angleDelta().y() > 0 else -1
            modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
            if modifiers & QtCore.Qt.ShiftModifier:
                self.wheel_amp.emit(delta)
            else:
                self.wheel_time.emit(delta)
            return False

        # 左键点击 → 找最近的 Y offset → 触发 channel_clicked
        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):
            if self._mode == "row":
                # 确定事件来源的 PlotWidget
                pw = self._left_pw if obj in (
                    self._left_pw.viewport(),
                    self._left_pw.scene()) else self._right_pw
                # 将 viewport 像素坐标转换为数据坐标
                vb = pw.getPlotItem().getViewBox()
                data_pt = vb.mapToView(pg.Point(event.pos()))
                y = float(data_pt.y())
                ch = int(np.argmin(np.abs(self._y_offsets - y)))
                if 0 <= ch < self._sd.n_chan:
                    self.channel_clicked.emit(ch)
                return True

        return False
