"""
grid.py — 网格视图（窗口裁剪 + 对象池 + 零线 + 斑马纹）

  GridView  : Row 模式 + Tile 模式。
              仅创建可见通道曲线（对象池），每条曲线只存当前时窗数据。
              播放时每帧更新可见窗口，滚动时换绑通道 + 更新窗口。

  信号:
    channel_clicked(int) — 点击了某个通道（绝对索引）
    wheel_time(int)      — +1 放大时窗, -1 缩小
    wheel_amp(int)       — +1 拉大幅值, -1 缩小
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

MAX_POINTS_PER_CURVE = 6000


class GridView(QtWidgets.QWidget):
    """网格视图 — 窗口裁剪 + 对象池 + 零线 + 斑马纹。

    - Row 模式: VISIBLE_ROWS 条曲线/侧，一通道一行，垂直堆叠
    - Tile 模式: VISIBLE_TILE_ROWS × TILE_COLS 个栅格/侧
    - 每条曲线只存 window_pts 个点
    - 每个通道有零基线（基准线）
    - 交替行背景（斑马纹）防止串行
    """

    channel_clicked = QtCore.pyqtSignal(int)
    wheel_time = QtCore.pyqtSignal(int)
    wheel_amp = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd
        self._mode = "row"
        self._y_offsets: np.ndarray = None
        self._total_height: float = 0.0
        self._ch_offset: int = 0
        self._last_ptr: int = -1

        # 对象池
        self._curves_orig: list[pg.PlotDataItem] = []
        self._curves_recon: list[pg.PlotDataItem] = []
        self._labels_l: list[pg.TextItem] = []   # 左侧标签
        self._labels_r: list[pg.TextItem] = []   # 右侧标签
        self._zero_lines_l: list[pg.InfiniteLine] = []  # 左侧零线
        self._zero_lines_r: list[pg.InfiniteLine] = []  # 右侧零线
        self._zebra_rects: list[pg.LinearRegionItem] = []  # 斑马纹
        self._tiles_orig: dict[tuple, tuple] = {}
        self._tiles_recon: dict[tuple, tuple] = {}

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    # UI 框架
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        root = QtWidgets.QStackedLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Row 模式 ─────────────────────────────────────
        self._row_widget = QtWidgets.QWidget()
        row_lay = QtWidgets.QHBoxLayout(self._row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(0)

        self._left_pw = pg.PlotWidget(background=COLOR_CARD)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        self._sep_v = self._make_vsep()
        self._sep_v.setStyleSheet(
            f"border: none; background-color: {COLOR_SEP};")

        self._right_pw = pg.PlotWidget(background=COLOR_CARD)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        self._left_vb.sigYRangeChanged.connect(self._sync_y_range)

        row_lay.addWidget(self._left_pw, 1)
        row_lay.addWidget(self._sep_v)
        row_lay.addWidget(self._right_pw, 1)

        # ── Tile 模式 ────────────────────────────────────
        self._tile_widget = QtWidgets.QWidget()
        tile_lay = QtWidgets.QHBoxLayout(self._tile_widget)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_lay.setSpacing(0)

        self._tile_left = pg.GraphicsLayoutWidget()
        self._tile_left.setBackground(COLOR_CARD)
        self._tile_right = pg.GraphicsLayoutWidget()
        self._tile_right.setBackground(COLOR_CARD)

        tile_lay.addWidget(self._tile_left, 1)
        tile_lay.addWidget(self._make_vsep())
        tile_lay.addWidget(self._tile_right, 1)

        root.addWidget(self._row_widget)
        root.addWidget(self._tile_widget)

        self._left_pw.viewport().installEventFilter(self)
        self._right_pw.viewport().installEventFilter(self)
        self._left_pw.scene().installEventFilter(self)
        self._right_pw.scene().installEventFilter(self)

    @staticmethod
    def _make_vsep():
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        f.setFixedWidth(2)
        return f

    def _config_plot(self, pi: pg.PlotItem):
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.showAxis('bottom')
        pi.setLabel('bottom', 'Time', units='s')

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
        self._total_height = float(sd.total_y_height)
        self._ch_offset = 0
        self._last_ptr = -1

        if self._mode == "row":
            self._build_row_pool(sd)
        else:
            self._build_tile_pool(sd)

    def _build_row_pool(self, sd: SignalData):
        """Row 模式：创建 VISIBLE_ROWS 条曲线 + 零线 + 斑马纹 + 左右标签。"""
        n_pool = min(VISIBLE_ROWS, sd.n_chan)
        w = sd.window_sec
        row_h = self._total_height / max(1, sd.n_chan)

        # 斑马纹 — 交替行背景
        for i in range(n_pool):
            if i % 2 == 1:
                continue
            abs_ch = i
            offset = float(self._y_offsets[abs_ch])
            zebra = pg.LinearRegionItem(
                values=[offset - row_h / 2, offset + row_h / 2],
                orientation='horizontal',
                brush=pg.mkBrush(COLOR_ZEBRA),
                pen=pg.mkPen(None))
            zebra.setMovable(False)
            self._left_pi.addItem(zebra)
            self._zebra_rects.append(zebra)

        # 曲线 + 零线 + 标签
        for i in range(n_pool):
            abs_ch = i
            offset = float(self._y_offsets[abs_ch])

            # 零基线（虚线）
            zl = pg.InfiniteLine(pos=offset, angle=0,
                                  pen=pg.mkPen(color=COLOR_GRID, width=0.5,
                                               style=QtCore.Qt.DashLine))
            zr = pg.InfiniteLine(pos=offset, angle=0,
                                  pen=pg.mkPen(color=COLOR_GRID, width=0.5,
                                               style=QtCore.Qt.DashLine))
            self._left_pi.addItem(zl)
            self._right_pi.addItem(zr)
            self._zero_lines_l.append(zl)
            self._zero_lines_r.append(zr)

            # 信号曲线
            c_l = self._left_pi.plot(pen=make_pen(COLOR_ORIG, LINE_WIDTH))
            c_l.setDownsampling(auto=False)
            c_l.setSkipFiniteCheck(True)
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

        self._fill_row_data(sd, 0)

        self._left_vb.setXRange(0, w, padding=0)
        self._right_vb.setXRange(0, w, padding=0)

        self._left_vb.setYRange(
            max(0, self._total_height - n_pool * row_h),
            self._total_height, padding=0)
        self._right_vb.setYRange(
            max(0, self._total_height - n_pool * row_h),
            self._total_height, padding=0)

    def _build_tile_pool(self, sd: SignalData):
        """Tile 模式：创建可见栅格。"""
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
                y_lo, y_hi = -ch_amp * 1.2, ch_amp * 1.2

                pi_l = self._tile_left.addPlot(row=r, col=c)
                self._config_tile_plot(pi_l, abs_ch, font, y_lo, y_hi)
                _add_tile_zero_line(pi_l, y_lo, y_hi)
                c_l = pi_l.plot(pen=make_pen(COLOR_ORIG, 0.4))
                c_l.setDownsampling(auto=False)
                c_l.setSkipFiniteCheck(True)
                self._tiles_orig[(r, c)] = (pi_l, c_l)

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
    # 数据填充
    # ═══════════════════════════════════════════════════════════

    def _fill_row_data(self, sd: SignalData, ptr: int):
        """Row 模式：填充当前窗口数据 + 更新零线/斑马纹/标签位置。"""
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        t = np.arange(wp, dtype=np.float32) / sd.s_freq
        t, wp = _clip_to_screen(t, wp)

        n_pool = len(self._curves_orig)
        row_h = self._total_height / max(1, sd.n_chan)

        for i in range(n_pool):
            abs_ch = self._ch_offset + i
            active = abs_ch < sd.n_chan

            if active:
                offset = float(self._y_offsets[abs_ch])
                self._curves_orig[i].setData(
                    t, sd.orig[abs_ch, t_slice][:wp] + offset)
                self._curves_recon[i].setData(
                    t, sd.recon[abs_ch, t_slice][:wp] + offset)
            else:
                offset = 0.0

            vis = active
            self._curves_orig[i].setVisible(vis)
            self._curves_recon[i].setVisible(vis)

            # 零线
            if i < len(self._zero_lines_l):
                self._zero_lines_l[i].setPos(offset)
                self._zero_lines_l[i].setVisible(vis)
            if i < len(self._zero_lines_r):
                self._zero_lines_r[i].setPos(offset)
                self._zero_lines_r[i].setVisible(vis)

            # 标签
            lbl_text = format_channel_label(abs_ch) if active else ""
            if i < len(self._labels_l):
                self._labels_l[i].setText(lbl_text)
                self._labels_l[i].setPos(0.0005, offset)
            if i < len(self._labels_r):
                self._labels_r[i].setText(lbl_text)
                self._labels_r[i].setPos(sd.window_sec - 0.0005, offset)

            # 斑马纹（仅偶数 i）
            zi = i // 2
            if i % 2 == 0 and zi < len(self._zebra_rects):
                if active:
                    rgn = self._zebra_rects[zi]
                    rgn.setRegion([offset - row_h / 2, offset + row_h / 2])
                    rgn.setVisible(True)
                else:
                    self._zebra_rects[zi].setVisible(False)

    def _fill_tile_data(self, sd: SignalData, ptr: int):
        """Tile 模式：给可见栅格填充当前窗口数据。"""
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        t = np.arange(wp, dtype=np.float32) / sd.s_freq
        t, wp = _clip_to_screen(t, wp)

        for (r, c), (pi, curve) in list(self._tiles_orig.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch >= sd.n_chan:
                continue
            ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
            pi.setYRange(-ch_amp * 1.2, ch_amp * 1.2, padding=0)
            curve.setData(t, sd.orig[abs_ch, t_slice][:wp])
            _update_tile_label(pi, abs_ch)

        for (r, c), (pi, curve) in list(self._tiles_recon.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch >= sd.n_chan:
                continue
            ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
            pi.setYRange(-ch_amp * 1.2, ch_amp * 1.2, padding=0)
            curve.setData(t, sd.recon[abs_ch, t_slice][:wp])

    # ═══════════════════════════════════════════════════════════
    # 视口同步
    # ═══════════════════════════════════════════════════════════

    def _sync_y_range(self, vb, range_):
        try:
            self._right_vb.blockSignals(True)
            self._right_vb.setYRange(*range_, padding=0)
        finally:
            self._right_vb.blockSignals(False)

    # ═══════════════════════════════════════════════════════════
    # 播放
    # ═══════════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        if ptr == self._last_ptr:
            return
        self._last_ptr = ptr

        if self._mode == "row":
            self._fill_row_data(sd, ptr)
        else:
            self._fill_tile_data(sd, ptr)

    # ═══════════════════════════════════════════════════════════
    # 通道滚动
    # ═══════════════════════════════════════════════════════════

    def set_offset(self, sd: SignalData, val: int):
        if not sd.ready:
            return
        val = max(0, min(val, sd.max_channel_offset))
        if val == self._ch_offset:
            return
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

    # ═══════════════════════════════════════════════════════════
    # 范围更新
    # ═══════════════════════════════════════════════════════════

    def update_ranges(self, sd: SignalData):
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
    # 事件过滤
    # ═══════════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        if not self._sd.ready or self._y_offsets is None:
            return False

        if event.type() == QtCore.QEvent.Wheel:
            delta = 1 if event.angleDelta().y() > 0 else -1
            modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
            if modifiers & QtCore.Qt.ShiftModifier:
                self.wheel_amp.emit(delta)
            else:
                self.wheel_time.emit(delta)
            return False

        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):
            if self._mode == "row":
                pw = self._left_pw if obj in (
                    self._left_pw.viewport(),
                    self._left_pw.scene()) else self._right_pw
                vb = pw.getPlotItem().getViewBox()
                data_pt = vb.mapToView(pg.Point(event.pos()))
                y = float(data_pt.y())
                ch = int(np.argmin(np.abs(self._y_offsets - y)))
                if 0 <= ch < self._sd.n_chan:
                    self.channel_clicked.emit(ch)
                return True

        return False


# ═══════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════

def _clip_to_screen(t: np.ndarray, wp: int) -> tuple[np.ndarray, int]:
    if wp > MAX_POINTS_PER_CURVE:
        step = wp // MAX_POINTS_PER_CURVE + 1
        return t[::step], len(t[::step])
    return t, wp


def _update_tile_label(pi: pg.PlotItem, ch: int):
    for item in pi.items:
        if isinstance(item, pg.TextItem):
            item.setText(format_channel_label(ch))
            break


def _add_tile_zero_line(pi: pg.PlotItem, y_lo: float, y_hi: float):
    """在 tile PlotItem 中添加零基准线。"""
    line = pg.InfiniteLine(pos=0, angle=0,
                            pen=pg.mkPen(color=COLOR_GRID, width=0.5,
                                         style=QtCore.Qt.DashLine))
    pi.addItem(line)