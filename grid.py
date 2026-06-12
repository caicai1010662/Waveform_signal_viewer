"""
grid.py — 网格视图（核心渲染模块）

  负责将 2048 通道的神经信号高效渲染到屏幕上。

  核心设计:
    1. 对象池 (Object Pool)    — 只创建 VISIBLE_ROWS 条曲线，滚动时复用
    2. 窗口裁剪 (Window Clipping)— 每条曲线只存 window_pts(~1500) 个点
    3. 视口剔除 (Viewport Culling)— 只渲染看得见的通道
    4. 斑马纹 (Zebra Striping)  — 交替行背景防止串行

  Trace 模式 (Row): VISIBLE_ROWS 条曲线，一通道一行，垂直堆叠
  Grid 模式 (Tile): VISIBLE_TILE_ROWS × TILE_COLS 个栅格

  调参入口: 本模块顶部的常量，改完保存 → 重启即可生效。
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from config import (COLOR_BG, COLOR_CARD, COLOR_SIGNAL,
                     COLOR_TEXT, COLOR_ZEBRA, FONT_SIZE)
from data import SignalData, SPACING_FACTOR
from utils import make_font, make_pen, format_channel_label


# ═══════════════════════════════════════════════════════════════
# 模块参数 — 调这里，不用去 config.py
# ═══════════════════════════════════════════════════════════════

# Grid 模式每行格子数。6 = 一行 6 个通道
TILE_COLS = 6

# Trace 模式一屏可见行数。6 = 同时显示 6 个通道
VISIBLE_ROWS = 6

# Grid 模式一屏可见行数。4 = 同时 4 行 × 6 列 = 24 通道
VISIBLE_TILE_ROWS = 4

# 波形线宽（像素）
LINE_WIDTH = 1.2

# 每曲线最大数据点数。超过此数 → 每隔 N 个取 1 个（简单步进降采样）
MAX_POINTS_PER_CURVE = 6000


class GridView(QtWidgets.QWidget):
    """网格视图 — 窗口裁剪 + 对象池 + 斑马纹。

    信号:
        channel_clicked(int) — 用户点击某通道，发射绝对通道索引

    内部模式:
        "row"  — 一行一通道（Trace 按钮）
        "tile" — 栅格模式（Grid 按钮）
    """

    channel_clicked = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd
        self._mode = "row"

        # ── Y 轴偏移（8KB，存所有 2048 通道的 Y 中心位置）──
        self._y_offsets: np.ndarray = None

        # ── 视口状态 ──────────────────────────────────────
        self._ch_offset: int = 0
        self._last_ptr: int = -1

        # ── 对象池（只存 VISIBLE_ROWS 个对象）────
        self._curves: list[pg.PlotDataItem] = []
        self._labels: list[pg.TextItem] = []
        self._zebra_rects: list[pg.LinearRegionItem] = []

        # ── 时间轴缓冲区（复用）────
        self._t_buf = np.empty(0, dtype=np.float32)

        # ── Tile 模式专用 ─────
        self._tiles: dict[tuple, tuple] = {}   # (row,col) → (PlotItem, curve, label)

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    # UI 框架
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        """构建双层 UI：Row 面板（索引 0）+ Tile 面板（索引 1）。"""
        root = QtWidgets.QStackedLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Row 模式面板 ───
        self._row_widget = QtWidgets.QWidget()
        self._row_widget.setStyleSheet(f"background-color: {COLOR_CARD};")
        row_lay = QtWidgets.QHBoxLayout(self._row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(0)

        self._pw = pg.PlotWidget(background=COLOR_CARD)
        self._pi = self._pw.getPlotItem()
        self._vb = self._pi.getViewBox()
        self._config_plot(self._pi)
        row_lay.addWidget(self._pw, 1)

        # ── Tile 模式面板 ───
        self._tile_widget = QtWidgets.QWidget()
        self._tile_widget.setStyleSheet(f"background-color: {COLOR_CARD};")
        tile_lay = QtWidgets.QHBoxLayout(self._tile_widget)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_lay.setSpacing(0)

        self._tile_grid = pg.GraphicsLayoutWidget()
        self._tile_grid.setBackground(COLOR_BG)
        self._tile_grid.ci.layout.setSpacing(2)
        tile_lay.addWidget(self._tile_grid, 1)

        root.addWidget(self._row_widget)
        root.addWidget(self._tile_widget)

        # 事件过滤
        self._pw.viewport().installEventFilter(self)
        self._tile_grid.viewport().installEventFilter(self)

    def _config_plot(self, pi: pg.PlotItem):
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
    # 构建
    # ═══════════════════════════════════════════════════════════

    def build(self):
        self.clear()
        sd = self._sd
        if not sd.ready:
            return

        self._y_offsets = sd.y_offsets_all()
        self._ch_offset = 0
        self._last_ptr = -1

        if self._mode == "row":
            self._build_row_pool(sd)
        else:
            self._build_tile_pool(sd)

    def _build_row_pool(self, sd: SignalData):
        n_pool = min(VISIBLE_ROWS, sd.n_chan)
        w = sd.window_sec

        # 斑马纹 — 偶数行
        for i in range(n_pool):
            if i % 2 == 1:
                continue
            zebra = pg.LinearRegionItem(
                values=[0, 1], orientation='horizontal',
                brush=pg.mkBrush(COLOR_ZEBRA), pen=pg.mkPen(None))
            zebra.setMovable(False)
            self._pi.addItem(zebra)
            self._zebra_rects.append(zebra)

        # 曲线 + 标签
        for i in range(n_pool):
            bg_color = COLOR_ZEBRA if i % 2 == 0 else COLOR_CARD

            c = self._pi.plot(pen=make_pen(COLOR_SIGNAL, LINE_WIDTH))
            c.setDownsampling(auto=False)
            c.setSkipFiniteCheck(True)
            self._curves.append(c)

            lbl = pg.TextItem("", color=COLOR_TEXT, anchor=(0, 1),
                              fill=pg.mkBrush(bg_color))
            lbl.setFont(make_font(FONT_SIZE))
            lbl.setZValue(100)
            self._pi.addItem(lbl)
            self._labels.append(lbl)

        self._fill_row_data(sd, 0)

        pad_x = w * 0.02
        self._vb.setXRange(-pad_x, w + pad_x, padding=0)
        self._update_row_yrange(sd)

    def _build_tile_pool(self, sd: SignalData):
        n_rows = min(VISIBLE_TILE_ROWS,
                     (sd.n_chan + TILE_COLS - 1) // TILE_COLS)
        w = sd.window_sec
        font = make_font(FONT_SIZE)

        for r in range(n_rows):
            for c in range(TILE_COLS):
                abs_ch = r * TILE_COLS + c
                if abs_ch >= sd.n_chan:
                    break
                ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
                y_lo, y_hi = -ch_amp * 1.2, ch_amp * 1.2

                pi = self._tile_grid.addPlot(row=r, col=c)
                lbl = self._config_tile_plot(pi, abs_ch, font, y_lo, y_hi)
                curve = pi.plot(pen=make_pen(COLOR_SIGNAL, LINE_WIDTH))
                curve.setDownsampling(auto=False)
                curve.setSkipFiniteCheck(True)
                self._tiles[(r, c)] = (pi, curve, lbl)

        self._fill_tile_data(sd, 0)

        for pi, _, _ in self._tiles.values():
            pi.setXRange(0, w, padding=0)

    def _config_tile_plot(self, pi: pg.PlotItem, ch: int,
                          font: QtGui.QFont, y_lo: float, y_hi: float):
        pi.getViewBox().setBackgroundColor(COLOR_CARD)
        # Tile 边框 — 区分相邻通道
        pi.getViewBox().setBorder(pg.mkPen(color="#474748", width=1.5))
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.hideAxis('bottom')
        pi.setYRange(y_lo, y_hi, padding=0)
        label = pg.TextItem(format_channel_label(ch),
                            color=COLOR_TEXT, anchor=(0, 1),
                            fill=pg.mkBrush(COLOR_CARD))
        label.setFont(font)
        label.setZValue(100)
        pi.addItem(label)
        label.setPos(0, y_lo + (y_hi - y_lo) * 0.02)
        return label

    def clear(self):
        self._pi.clear()
        self._tile_grid.clear()
        self._curves.clear()
        self._labels.clear()
        self._zebra_rects.clear()
        self._tiles.clear()

    # ═══════════════════════════════════════════════════════════
    # 数据填充
    # ═══════════════════════════════════════════════════════════

    def _fill_row_data(self, sd: SignalData, ptr: int):
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        if len(self._t_buf) != wp:
            self._t_buf = np.arange(wp, dtype=np.float32) / sd.s_freq
        t = self._t_buf
        t, wp = _step_decimate(t, wp)

        n_pool = len(self._curves)

        for i in range(n_pool):
            abs_ch = self._ch_offset + i
            active = abs_ch < sd.n_chan

            if active:
                offset = float(self._y_offsets[abs_ch])
                self._curves[i].setData(
                    t, sd.recon[abs_ch, t_slice][:wp] + offset)
                ch_h = float(sd.ch_amp[abs_ch]) * SPACING_FACTOR * sd.amp_scale
            else:
                offset = 0.0
                ch_h = 1.0

            vis = active
            self._curves[i].setVisible(vis)

            # 标签
            lbl_text = format_channel_label(abs_ch) if active else ""
            x_margin = sd.window_sec * 0.01
            y_bottom = offset - ch_h / 2.0 + (ch_h * 0.05)
            if i < len(self._labels):
                self._labels[i].setText(lbl_text)
                self._labels[i].setPos(x_margin, y_bottom)
                self._labels[i].setVisible(vis)

            # 斑马纹
            zi = i // 2
            if i % 2 == 0 and zi < len(self._zebra_rects):
                if active:
                    bounds = [offset - ch_h / 2.0, offset + ch_h / 2.0]
                    self._zebra_rects[zi].setRegion(bounds)
                    self._zebra_rects[zi].setVisible(True)
                else:
                    self._zebra_rects[zi].setVisible(False)

    def _fill_tile_data(self, sd: SignalData, ptr: int):
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        if len(self._t_buf) != wp:
            self._t_buf = np.arange(wp, dtype=np.float32) / sd.s_freq
        t = self._t_buf
        t, wp = _step_decimate(t, wp)

        for (r, c), (pi, curve, label) in self._tiles.items():
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch < sd.n_chan:
                curve.setData(t, sd.recon[abs_ch, t_slice][:wp])
                curve.setVisible(True)
                label.setText(format_channel_label(abs_ch))
                label.setVisible(True)
                ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
                y_lo = -ch_amp * 1.2
                y_hi = ch_amp * 1.2
                label.setPos(0, y_lo + (y_hi - y_lo) * 0.02)
                pi.setYRange(y_lo, y_hi, padding=0)
            else:
                curve.setVisible(False)
                label.setVisible(False)

    # ═══════════════════════════════════════════════════════════
    # 外部接口（由 app.py 调用）
    # ═══════════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        if ptr == self._last_ptr:
            return
        self._last_ptr = ptr
        if self._mode == "row":
            self._fill_row_data(sd, ptr)
        else:
            self._fill_tile_data(sd, ptr)

    def set_offset(self, sd: SignalData, val: int):
        if not sd.ready:
            return
        per_page = (VISIBLE_ROWS if self._mode == "row"
                    else TILE_COLS * VISIBLE_TILE_ROWS)
        val = max(0, min(val, sd.max_channel_offset(per_page)))
        if val == self._ch_offset:
            return
        self._ch_offset = val
        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            self._update_row_yrange(sd)
        else:
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def update_ranges(self, sd: SignalData):
        w = sd.window_sec
        if self._mode == "row":
            pad_x = w * 0.02
            self._vb.setXRange(-pad_x, w + pad_x, padding=0)
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
        else:
            for pi, _, _ in self._tiles.values():
                pi.setXRange(0, w, padding=0)
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def reload_amp(self, sd: SignalData):
        if not sd.ready:
            return
        self._y_offsets = sd.y_offsets_all()
        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            self._update_row_yrange(sd)
        else:
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def _update_row_yrange(self, sd: SignalData):
        n_pool = len(self._curves)
        if n_pool == 0 or not sd.ready or self._y_offsets is None:
            return
        top_ch = self._ch_offset
        bot_ch = min(sd.n_chan - 1, self._ch_offset + n_pool - 1)
        top_h = float(sd.ch_amp[top_ch]) * SPACING_FACTOR * sd.amp_scale
        bot_h = float(sd.ch_amp[bot_ch]) * SPACING_FACTOR * sd.amp_scale
        y_top = self._y_offsets[top_ch] + top_h / 2.0
        y_bot = self._y_offsets[bot_ch] - bot_h / 2.0
        pad = (y_top - y_bot) * 0.05
        self._vb.setYRange(y_bot - pad, y_top + pad, padding=0)

    # ═══════════════════════════════════════════════════════════
    # 事件过滤 — 点击打开 Detail
    # ═══════════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        if not self._sd.ready or self._y_offsets is None:
            return False
        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):
            if self._mode == "row":
                vb = self._vb
                data_pt = vb.mapToView(pg.Point(event.pos()))
                ch = int(np.argmin(np.abs(self._y_offsets - float(data_pt.y()))))
                if 0 <= ch < self._sd.n_chan:
                    self.channel_clicked.emit(ch)
                return True
            elif self._mode == "tile":
                scene_pt = self._tile_grid.mapToScene(event.pos())
                for (r, c), (pi, _, _) in self._tiles.items():
                    if pi.getViewBox().sceneBoundingRect().contains(scene_pt):
                        abs_ch = self._ch_offset + r * TILE_COLS + c
                        if 0 <= abs_ch < self._sd.n_chan:
                            self.channel_clicked.emit(abs_ch)
                        return True
        return False


# ═══════════════════════════════════════════════════════════════
# 模块级工具
# ═══════════════════════════════════════════════════════════════

def _step_decimate(t: np.ndarray, wp: int) -> tuple[np.ndarray, int]:
    if wp > MAX_POINTS_PER_CURVE:
        step = wp // MAX_POINTS_PER_CURVE + 1
        return t[::step], len(t[::step])
    return t, wp
