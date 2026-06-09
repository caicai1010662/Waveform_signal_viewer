"""
oscilloscope.py — 示波器滚动模式

  OscilloscopeView  : 类似传统示波器，波形从左端出现向右滚动。
                      左侧 = 原始信号 (白色), 右侧 = 重建信号 (黄色)。
                      8-16 通道堆叠显示，支持选择通道范围。

  信号:
    channel_clicked(int) — 点击通道
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_BG, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_SEP, WINDOW_SEC, LINE_WIDTH,
                     SPACING_FACTOR, DECIMATION_TARGET)
from data import SignalData
from utils import make_font, format_channel_label


class OscilloscopeView(QtWidgets.QWidget):
    """示波器滚动模式。

    波形从右端出现，向左滚动，模拟传统示波器。
    同步左右两个 ViewBox（原始/重建）。
    """

    channel_clicked = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd
        self._visible_channels: int = 8     # 默认显示 8 通道
        self._ch_start: int = 0             # 起始通道
        self._y_offsets: np.ndarray = None
        self._total_height: float = 0.0
        self._curves_orig: dict[int, pg.PlotDataItem] = {}
        self._curves_recon: dict[int, pg.PlotDataItem] = {}
        self._labels: dict[int, pg.TextItem] = {}

        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧 ViewBox — 原始
        self._left_pw = pg.PlotWidget(background=COLOR_BG)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        # 分隔线
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        sep.setFixedWidth(1)

        # 右侧 ViewBox — 重建
        self._right_pw = pg.PlotWidget(background=COLOR_BG)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        layout.addWidget(self._left_pw, 1)
        layout.addWidget(sep)
        layout.addWidget(self._right_pw, 1)

        # Y 同步
        self._left_vb.sigYRangeChanged.connect(self._sync_y)

        # 事件
        self._left_pw.viewport().installEventFilter(self)
        self._right_pw.viewport().installEventFilter(self)

    def _config_plot(self, pi: pg.PlotItem):
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.hideAxis('bottom')

    def _sync_y(self, vb, range_):
        try:
            self._right_vb.blockSignals(True)
            self._right_vb.setYRange(*range_, padding=0)
        finally:
            self._right_vb.blockSignals(False)

    # ── 构建 ──────────────────────────────────────────────

    def build(self):
        """为可见通道创建曲线对象。"""
        self.clear()
        sd = self._sd
        if not sd.ready:
            return

        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)

        font = make_font(8)
        w = sd.window_sec

        for ch in range(self._visible_channels):
            abs_ch = self._ch_start + ch
            if abs_ch >= sd.n_chan:
                break
            offset = float(self._y_offsets[abs_ch])

            c_orig = self._left_pi.plot(
                pen=pg.mkPen(color=COLOR_ORIG, width=LINE_WIDTH))
            c_orig.setDownsampling(auto=False)
            c_orig.setSkipFiniteCheck(True)
            self._curves_orig[abs_ch] = c_orig

            c_recon = self._right_pi.plot(
                pen=pg.mkPen(color=COLOR_RECON, width=LINE_WIDTH))
            c_recon.setDownsampling(auto=False)
            c_recon.setSkipFiniteCheck(True)
            self._curves_recon[abs_ch] = c_recon

            lbl = pg.TextItem(format_channel_label(abs_ch),
                              color=COLOR_TEXT, anchor=(0, 0.5))
            lbl.setFont(font)
            self._left_pi.addItem(lbl)
            lbl.setPos(0.0005, offset)
            self._labels[abs_ch] = lbl

        self._left_vb.setXRange(0, w, padding=0)
        self._right_vb.setXRange(0, w, padding=0)

        n_show = min(self._visible_channels, sd.n_chan - self._ch_start)
        row_h = self._total_height / max(1, sd.n_chan)
        bot = self._y_offsets[self._ch_start + n_show - 1] - row_h
        top = self._y_offsets[self._ch_start] + row_h
        self._left_vb.setYRange(bot, top, padding=0)
        self._right_vb.setYRange(bot, top, padding=0)

    def clear(self):
        self._left_pi.clear()
        self._right_pi.clear()
        self._curves_orig.clear()
        self._curves_recon.clear()
        self._labels.clear()

    # ── 播放滚动 ──────────────────────────────────────────

    def scroll(self, ptr: int, sd: SignalData):
        """播放时：为可见通道写入新数据（示波器滚动效果）。"""
        if not sd.ready:
            return
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            return

        t = np.arange(wp, dtype=np.float32) / sd.s_freq

        for abs_ch in list(self._curves_orig.keys()):
            if abs_ch < sd.n_chan:
                offset = float(self._y_offsets[abs_ch])
                self._curves_orig[abs_ch].setData(
                    t, sd.orig[abs_ch, ptr:ptr + wp] + offset)
                self._curves_recon[abs_ch].setData(
                    t, sd.recon[abs_ch, ptr:ptr + wp] + offset)

    # ── 通道范围 ──────────────────────────────────────────

    def set_channel_range(self, start: int, count: int):
        """设置可见通道范围。"""
        sd = self._sd
        if not sd.ready:
            self._ch_start = start
            self._visible_channels = count
            return
        self._ch_start = max(0, min(start, sd.n_chan - count))
        self._visible_channels = count
        self.build()

    # ── 事件 ──────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if not self._sd.ready or self._y_offsets is None:
            return False

        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):
            pw = self._left_pw if obj == self._left_pw.viewport() else self._right_pw
            vb = pw.getPlotItem().getViewBox()
            data_pt = vb.mapToView(pg.Point(event.pos()))
            y = float(data_pt.y())
            keys = list(self._curves_orig.keys())
            if keys:
                offsets_for_keys = np.array(
                    [self._y_offsets[k] for k in keys])
                idx = int(np.argmin(np.abs(offsets_for_keys - y)))
                self.channel_clicked.emit(keys[idx])
            return True

        return False
