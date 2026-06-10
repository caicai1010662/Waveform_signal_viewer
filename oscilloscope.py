"""
oscilloscope.py — 示波器滚动模式（Roll 模式）

  OscilloscopeView : 模拟传统示波器。波形从右端出现向左滚动。
                     左右两个 ViewBox（原始 / 重建），同步 Y 轴。
                     默认显示 8 个通道，堆叠排列。

  与 GridView 的区别:
    GridView  — 静态窗口，播放时每帧更新当前窗口数据（setData 换内容）
    OscilloscopeView — 滚动式，播放时也每帧 setData 换内容（视觉效果不同）

  调参入口: 无。通道范围由 app.py 调用 set_channel_range() 设置。
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

    信号:
        channel_clicked(int) — 用户点击某个通道时发射
    """

    channel_clicked = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd

        # ── 通道范围 ──────────────────────────────────────
        self._visible_channels: int = 8     # 一屏显示的通道数
        self._ch_start: int = 0             # 起始通道索引

        # ── Y 偏移（从 SignalData 计算，8KB 内存）────────
        self._y_offsets: np.ndarray = None
        self._total_height: float = 0.0

        # ── 曲线和标签池（只存可见通道）──────────────────
        self._curves_orig: dict[int, pg.PlotDataItem] = {}
        self._curves_recon: dict[int, pg.PlotDataItem] = {}
        self._labels: dict[int, pg.TextItem] = {}

        self._build_ui()

    # ═════════════════════════════════════════════════════
    # UI 框架
    # ═════════════════════════════════════════════════════

    def _build_ui(self):
        """构建左右两个 PlotWidget + 中间分隔线。"""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧 — 原始信号
        self._left_pw = pg.PlotWidget(background=COLOR_BG)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        # 中间分隔线
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        sep.setFixedWidth(1)

        # 右侧 — 重建信号
        self._right_pw = pg.PlotWidget(background=COLOR_BG)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        layout.addWidget(self._left_pw, 1)
        layout.addWidget(sep)
        layout.addWidget(self._right_pw, 1)

        # 左右 Y 轴同步（拖动一侧时另一侧跟随）
        self._left_vb.sigYRangeChanged.connect(self._sync_y)

        # 事件过滤（点击通道 → 打开详情窗）
        self._left_pw.viewport().installEventFilter(self)
        self._right_pw.viewport().installEventFilter(self)

    def _config_plot(self, pi: pg.PlotItem):
        """配置 PlotItem：隐藏按钮和坐标轴。"""
        pi.hideButtons()
        pi.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        pi.hideAxis('left')
        pi.hideAxis('bottom')

    def _sync_y(self, vb, range_):
        """左侧 Y 范围变化 → 同步右侧。blockSignals 防止递归触发。"""
        try:
            self._right_vb.blockSignals(True)
            self._right_vb.setYRange(*range_, padding=0)
        finally:
            self._right_vb.blockSignals(False)

    # ═════════════════════════════════════════════════════
    # 构建 — 为可见通道创建曲线和标签
    # ═════════════════════════════════════════════════════

    def build(self):
        """(重)构建所有可见通道的曲线对象。数据变化时调用。"""
        self.clear()
        sd = self._sd
        if not sd.ready:
            return

        # 计算所有通道的 Y 偏移
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)

        font = make_font(8)
        w = sd.window_sec

        # 为每个可见通道创建一对曲线 + 标签
        for ch in range(self._visible_channels):
            abs_ch = self._ch_start + ch
            if abs_ch >= sd.n_chan:
                break
            offset = float(self._y_offsets[abs_ch])

            # 左侧 — 原始信号曲线
            c_orig = self._left_pi.plot(
                pen=pg.mkPen(color=COLOR_ORIG, width=LINE_WIDTH))
            c_orig.setDownsampling(auto=False)
            c_orig.setSkipFiniteCheck(True)
            self._curves_orig[abs_ch] = c_orig

            # 右侧 — 重建信号曲线
            c_recon = self._right_pi.plot(
                pen=pg.mkPen(color=COLOR_RECON, width=LINE_WIDTH))
            c_recon.setDownsampling(auto=False)
            c_recon.setSkipFiniteCheck(True)
            self._curves_recon[abs_ch] = c_recon

            # 通道标签
            lbl = pg.TextItem(format_channel_label(abs_ch),
                              color=COLOR_TEXT, anchor=(0, 0.5))
            lbl.setFont(font)
            self._left_pi.addItem(lbl)
            lbl.setPos(0.0005, offset)
            self._labels[abs_ch] = lbl

        # 设置 X/Y 范围
        self._left_vb.setXRange(0, w, padding=0)
        self._right_vb.setXRange(0, w, padding=0)

        n_show = min(self._visible_channels, sd.n_chan - self._ch_start)
        row_h = self._total_height / max(1, sd.n_chan)
        # Y 范围: 从最后一个可见通道的底部到第一个的顶部
        bot = self._y_offsets[self._ch_start + n_show - 1] - row_h
        top = self._y_offsets[self._ch_start] + row_h
        self._left_vb.setYRange(bot, top, padding=0)
        self._right_vb.setYRange(bot, top, padding=0)

    def clear(self):
        """清空所有曲线和标签。"""
        self._left_pi.clear()
        self._right_pi.clear()
        self._curves_orig.clear()
        self._curves_recon.clear()
        self._labels.clear()

    # ═════════════════════════════════════════════════════
    # 播放 — 每帧更新窗口数据
    # ═════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        """播放时每帧调用：为可见通道写入当前窗口数据。

        与 GridView.scroll() 功能相同：从 memmap 读取数据 → setData 到曲线。
        """
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

    # ═════════════════════════════════════════════════════
    # 通道范围设置
    # ═════════════════════════════════════════════════════

    def set_channel_range(self, start: int, count: int):
        """设置可见通道范围（起始通道 + 数量）。

        Args:
            start: 起始通道索引（0-based）
            count: 显示通道数（默认 8）

        如果数据尚未加载，先存储参数，等 build() 时使用。
        """
        sd = self._sd
        if not sd.ready:
            self._ch_start = start
            self._visible_channels = count
            return
        self._ch_start = max(0, min(start, sd.n_chan - count))
        self._visible_channels = count
        self.build()

    # ═════════════════════════════════════════════════════
    # 事件过滤 — 点击通道 → 打开详情窗
    # ═════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        if not self._sd.ready or self._y_offsets is None:
            return False

        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):
            # 确定是左侧还是右侧的点击
            pw = self._left_pw if obj == self._left_pw.viewport() else self._right_pw
            vb = pw.getPlotItem().getViewBox()
            data_pt = vb.mapToView(pg.Point(event.pos()))
            y = float(data_pt.y())

            # 找最近 Y 偏移 → 确定点击的通道
            keys = list(self._curves_orig.keys())
            if keys:
                offsets_for_keys = np.array(
                    [self._y_offsets[k] for k in keys])
                idx = int(np.argmin(np.abs(offsets_for_keys - y)))
                self.channel_clicked.emit(keys[idx])
            return True

        return False
