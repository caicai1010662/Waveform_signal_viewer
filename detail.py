"""
detail.py — 单通道详情弹出窗口

  DetailWindow : 点击通道后弹出的放大视图。
                 播放时每帧 setData，连接 Player.frame_ready。

  调参入口: 本模块顶部的常量，改完保存 → 重启即可生效。
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_BG, COLOR_SIGNAL, COLOR_GRID, COLOR_TEXT, FONT_FAMILY)
from data import SignalData
from player import Player
from utils import make_font


# ═══════════════════════════════════════════════════════════════
# 模块参数 — 调这里，不用去 config.py
# ═══════════════════════════════════════════════════════════════

# 字体字号
DETAIL_FONT_TICK  = 15        # 坐标轴刻度数字
DETAIL_FONT_LABEL = 50        # 坐标轴标题（µV / Time）
DETAIL_FONT_TITLE = 12        # 面板标题

# 视觉
DETAIL_GRID_ALPHA = 0.9       # 网格虚线透明度
DETAIL_LINE_WIDTH = 1.5       # 波形线宽（像素）
DETAIL_Y_PADDING  = 1.0       # Y 轴上下留白系数
DETAIL_X_PADDING  = 0.02      # X 轴左右呼吸空间（比例）

# 窗口偏移（相对于主窗口）
DETAIL_OFFSET_X = 30
DETAIL_OFFSET_Y = 30


class DetailWindow(QtWidgets.QMainWindow):
    """单通道放大窗口。

    生命周期:
      点击通道 → new DetailWindow → show → 跟随播放更新 → 关闭窗口 → disconnect
    """

    def __init__(self, ch: int, sd: SignalData, player: Player, parent=None):
        super().__init__(parent)
        self._ch = ch
        self._sd = sd
        self._player = player

        y_lo, y_hi = sd.y_range_detail(ch, DETAIL_Y_PADDING)
        amp = sd.ch_amp[ch] if sd.ch_amp is not None else 0.0
        self.setWindowTitle(f"Ch{ch + 1}  —  {amp:.1f}µV")
        self.resize(900, 420)

        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        main_v = QtWidgets.QVBoxLayout(cw)
        main_v.setContentsMargins(4, 25, 4, 15)
        main_v.setSpacing(4)

        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground(COLOR_BG)
        self._p = self._glw.addPlot()
        self._setup_axes(self._p)
        self._p.setYRange(y_lo, y_hi, padding=0)
        self._p.setXRange(0, sd.window_sec, padding=DETAIL_X_PADDING)

        self._curve = self._p.plot(
            pen=pg.mkPen(color=COLOR_SIGNAL, width=DETAIL_LINE_WIDTH))
        self._curve.setDownsampling(auto=False)

        main_v.addWidget(self._glw, 1)

        self._t_buf = np.empty(0, dtype=np.float32)
        player.frame_ready.connect(self._tick)
        self._tick()

    # ═════════════════════════════════════════════════════
    # 坐标轴
    # ═════════════════════════════════════════════════════

    def _setup_axes(self, p: pg.PlotItem):
        font_tick = make_font(DETAIL_FONT_TICK)
        label_style = f'{DETAIL_FONT_LABEL}pt'

        p.setLabel('left', 'µV', color=COLOR_TEXT,
                   size=label_style, family=FONT_FAMILY, bold=True)
        p.setLabel('bottom', 'Time', units='s', color=COLOR_TEXT,
                   size=label_style, family=FONT_FAMILY, bold=True)
        for ax_name in ('left', 'bottom'):
            ax = p.getAxis(ax_name)
            ax.setPen(pg.mkPen(color=COLOR_GRID, width=1))
            ax.setTextPen(COLOR_TEXT)
            self._force_axis_font(ax, font_tick)

        p.showGrid(x=True, y=True, alpha=DETAIL_GRID_ALPHA)
        p.hideButtons()
        p.setMouseEnabled(x=False, y=False)
        p.setMenuEnabled(False)

    @staticmethod
    def _force_axis_font(ax, tick_font: QtGui.QFont):
        ax.setTickFont(tick_font)
        for child in ax.childItems():
            if isinstance(child, QtWidgets.QGraphicsTextItem):
                child.setFont(tick_font)

    # ═════════════════════════════════════════════════════
    # 范围更新
    # ═════════════════════════════════════════════════════

    def update_ranges(self):
        sd = self._sd
        w = sd.window_sec
        y_lo, y_hi = sd.y_range_detail(self._ch, DETAIL_Y_PADDING)
        self._p.setXRange(0, w, padding=DETAIL_X_PADDING)
        self._p.setYRange(y_lo, y_hi, padding=0)

        amp = sd.ch_amp[self._ch] if sd.ch_amp is not None else 0.0
        self.setWindowTitle(f"Ch{self._ch + 1}  —  {amp:.1f}µV")

    # ═════════════════════════════════════════════════════
    # 帧更新
    # ═════════════════════════════════════════════════════

    def _tick(self):
        sd = self._sd
        if not sd.ready:
            return
        ptr = self._player.ptr
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            return

        if len(self._t_buf) != wp:
            self._t_buf = np.arange(wp, dtype=np.float32) / sd.s_freq

        self._curve.setData(
            self._t_buf, sd.recon[self._ch, ptr:ptr + wp])

    # ═════════════════════════════════════════════════════
    # 关闭
    # ═════════════════════════════════════════════════════

    def closeEvent(self, ev):
        try:
            self._player.frame_ready.disconnect(self._tick)
        except (TypeError, RuntimeError):
            pass
        ev.accept()
