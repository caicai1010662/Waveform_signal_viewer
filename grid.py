"""
grid.py — 网格视图（窗口裁剪 + 对象池）

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

from config import (COLOR_BG, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_SEP, TILE_COLS, VISIBLE_ROWS,
                     VISIBLE_TILE_ROWS, LINE_WIDTH, SPACING_FACTOR)
from data import SignalData
from utils import make_font, make_pen, format_channel_label

# 每条曲线最大点数 = 200ms × 30kHz ≈ 6000，远小于屏幕像素数时才降采样
MAX_POINTS_PER_CURVE = 6000


class GridView(QtWidgets.QWidget):
    """网格视图 — 窗口裁剪 + 对象池。

    - Row 模式: VISIBLE_ROWS 条曲线/侧，一通道一行，垂直堆叠
    - Tile 模式: VISIBLE_TILE_ROWS × TILE_COLS 个栅格/侧
    - 每条曲线只存 window_pts 个点（不存全量时间序列）
    - 播放: 每帧 setData 更新窗口
    - 滚动: 换绑通道 + 更新窗口
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
        self._last_ptr: int = -1          # 上次渲染的 ptr，避免重复更新

        # 对象池（只存可见数量）
        self._curves_orig: list[pg.PlotDataItem] = []
        self._curves_recon: list[pg.PlotDataItem] = []
        self._labels: list[pg.TextItem] = []
        self._tiles_orig: dict[tuple, tuple] = {}
        self._tiles_recon: dict[tuple, tuple] = {}

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    # UI 框架（只执行一次）
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

        self._left_pw = pg.PlotWidget(background=COLOR_BG)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        self._right_pw = pg.PlotWidget(background=COLOR_BG)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        self._left_vb.sigYRangeChanged.connect(self._sync_y_range)

        row_lay.addWidget(self._left_pw, 1)
        row_lay.addWidget(self._make_vsep())
        row_lay.addWidget(self._right_pw, 1)

        # ── Tile 模式 ────────────────────────────────────
        self._tile_widget = QtWidgets.QWidget()
        tile_lay = QtWidgets.QHBoxLayout(self._tile_widget)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_lay.setSpacing(0)

        self._tile_left = pg.GraphicsLayoutWidget()
        self._tile_left.setBackground(COLOR_BG)
        self._tile_right = pg.GraphicsLayoutWidget()
        self._tile_right.setBackground(COLOR_BG)

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
        f.setFixedWidth(1)
        return f

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
    # 构建 — 仅创建可见数量的曲线对象（对象池）
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
        """Row 模式：创建 VISIBLE_ROWS 条曲线对象（空池，等数据填充）。"""
        n_pool = min(VISIBLE_ROWS, sd.n_chan)
        w = sd.window_sec

        for _ in range(n_pool):
            c_l = self._left_pi.plot(pen=make_pen(COLOR_ORIG, LINE_WIDTH))
            c_l.setDownsampling(auto=False)
            c_l.setSkipFiniteCheck(True)
            self._curves_orig.append(c_l)

            c_r = self._right_pi.plot(pen=make_pen(COLOR_RECON, LINE_WIDTH))
            c_r.setDownsampling(auto=False)
            c_r.setSkipFiniteCheck(True)
            self._curves_recon.append(c_r)

            lbl = pg.TextItem("", color=COLOR_TEXT, anchor=(0, 0.5))
            lbl.setFont(make_font(8))
            self._left_pi.addItem(lbl)
            self._labels.append(lbl)

        # 填充初始数据
        self._fill_row_data(sd, 0)

        # 固定 X 范围
        self._left_vb.setXRange(0, w, padding=0)
        self._right_vb.setXRange(0, w, padding=0)

        # Y 范围
        row_h = self._total_height / max(1, sd.n_chan)
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
                c_l = pi_l.plot(pen=make_pen(COLOR_ORIG, 0.4))
                c_l.setDownsampling(auto=False)
                c_l.setSkipFiniteCheck(True)
                self._tiles_orig[(r, c)] = (pi_l, c_l)

                pi_r = self._tile_right.addPlot(row=r, col=c)
                self._config_tile_plot(pi_r, abs_ch, font, y_lo, y_hi)
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
        self._labels.clear()
        self._tiles_orig.clear()
        self._tiles_recon.clear()

    # ═══════════════════════════════════════════════════════════
    # 数据填充 — 只加载当前窗口的采样点
    # ═══════════════════════════════════════════════════════════

    def _fill_row_data(self, sd: SignalData, ptr: int):
        """Row 模式：给对象池曲线填充当前窗口数据。"""
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        t = np.arange(wp, dtype=np.float32) / sd.s_freq

        # 按屏幕像素裁剪
        t, wp = _clip_to_screen(t, wp)

        n_pool = len(self._curves_orig)
        for i in range(n_pool):
            abs_ch = self._ch_offset + i
            if abs_ch >= sd.n_chan:
                self._curves_orig[i].setVisible(False)
                self._curves_recon[i].setVisible(False)
                self._labels[i].setText("")
                continue
            self._curves_orig[i].setVisible(True)
            self._curves_recon[i].setVisible(True)

            offset = float(self._y_offsets[abs_ch])
            self._curves_orig[i].setData(
                t, sd.orig[abs_ch, t_slice][:wp] + offset)
            self._curves_recon[i].setData(
                t, sd.recon[abs_ch, t_slice][:wp] + offset)
            self._labels[i].setText(format_channel_label(abs_ch))
            self._labels[i].setPos(0.0005, offset)

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
    # 播放 — 每帧更新窗口数据
    # ═══════════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        """播放时每帧调用：更新可见通道的窗口数据。

        如果 ptr 没变就跳过（避免重复渲染）。
        """
        if ptr == self._last_ptr:
            return
        self._last_ptr = ptr

        if self._mode == "row":
            self._fill_row_data(sd, ptr)
        else:
            self._fill_tile_data(sd, ptr)

    # ═══════════════════════════════════════════════════════════
    # 通道滚动 — 换绑通道 + 填充当前窗口数据
    # ═══════════════════════════════════════════════════════════

    def set_offset(self, sd: SignalData, val: int):
        """竖向浏览：更新可见通道范围 + 重新填充数据。"""
        if not sd.ready:
            return
        val = max(0, min(val, sd.max_channel_offset))
        if val == self._ch_offset:
            return
        self._ch_offset = val

        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            # 更新 Y 视口
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
        """时窗变化：更新 X 范围 + 重新填充数据。"""
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
        """幅值缩放：重算 Y 偏移 + 更新数据 + Y 范围。"""
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
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _clip_to_screen(t: np.ndarray, wp: int) -> tuple[np.ndarray, int]:
    """如果点数超过屏幕分辨率，做简单的降采样（每隔 N 个取 1 个）。"""
    if wp > MAX_POINTS_PER_CURVE:
        step = wp // MAX_POINTS_PER_CURVE + 1
        return t[::step], len(t[::step])
    return t, wp


def _update_tile_label(pi: pg.PlotItem, ch: int):
    for item in pi.items:
        if isinstance(item, pg.TextItem):
            item.setText(format_channel_label(ch))
            break
