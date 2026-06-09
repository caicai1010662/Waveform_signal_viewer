"""
detail.py — 单通道详情弹出窗口

  DetailWindow  : 叠加对比模式（原始 + 重建叠在同一轴）
                  可切换左右并排模式。
                  播放时每帧 setData，连接 Player.frame_ready。
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_BG, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_CARD, FONT_FAMILY)
from data import SignalData
from player import Player
from decimator import lttb
from utils import make_font


class DetailWindow(QtWidgets.QMainWindow):
    """弹出窗口：单通道原始 vs 重建对比。

    默认 Overlay 模式（两条曲线在同一轴），可切换 Side-by-side 模式。
    """

    def __init__(self, ch: int, sd: SignalData, player: Player, parent=None):
        super().__init__(parent)
        self._ch = ch
        self._sd = sd
        self._player = player
        self._overlay = True  # True=叠加, False=并排

        y_lo, y_hi = sd.y_range_detail(ch)
        amp_val = sd.ch_amp[ch] if sd.ch_amp is not None else 0.0
        self.setWindowTitle(
            f"Ch{ch + 1}  —  Original vs Reconstructed  |  "
            f"Amplitude {amp_val:.1f} µV")
        self.resize(1200, 420)

        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)

        # 主垂直布局
        main_v = QtWidgets.QVBoxLayout(cw)
        main_v.setContentsMargins(4, 4, 4, 4)
        main_v.setSpacing(4)

        # ── 顶栏 ──────────────────────────────────────────
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(4, 2, 4, 2)

        self._btn_toggle = QtWidgets.QPushButton("Overlay Mode")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.setChecked(True)
        self._btn_toggle.clicked.connect(self._toggle_mode)

        self._lbl_info = QtWidgets.QLabel()
        self._lbl_info.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}'; font-size: 10px;")

        top.addWidget(self._btn_toggle)
        top.addStretch(1)
        top.addWidget(self._lbl_info)
        main_v.addLayout(top)

        # ── 波形区域 ──────────────────────────────────────
        self._stack = QtWidgets.QStackedLayout()
        main_v.addLayout(self._stack, 1)

        # Overlay 面板
        self._overlay_panel = self._make_overlay_panel(y_lo, y_hi)
        self._stack.addWidget(self._overlay_panel)

        # Side-by-side 面板
        self._side_panel = self._make_side_panel(y_lo, y_hi)
        self._stack.addWidget(self._side_panel)

        # 播放连接
        self._t_buf = np.empty(0, dtype=np.float32)
        player.frame_ready.connect(self._tick)
        self._tick()

    # ── 构建 Overlay 面板 ─────────────────────────────────

    def _make_overlay_panel(self, y_lo: float, y_hi: float) -> pg.GraphicsLayoutWidget:
        glw = pg.GraphicsLayoutWidget()
        glw.setBackground(COLOR_BG)
        p = glw.addPlot()
        p.setLabel('left', 'µV', color=COLOR_TEXT)
        p.setLabel('bottom', 'Time', units='s', color=COLOR_TEXT)
        for ax_name in ('left', 'bottom'):
            ax = p.getAxis(ax_name)
            ax.setPen(COLOR_GRID)
            ax.setTextPen(COLOR_TEXT)
            ax.setTickFont(make_font(9))
        p.showGrid(x=True, y=True, alpha=0.06)
        p.setYRange(y_lo, y_hi, padding=0)
        p.setXRange(0, self._sd.window_sec, padding=0)
        p.hideButtons()
        p.setMouseEnabled(x=False, y=False)
        p.setMenuEnabled(False)
        p.addLegend(offset=(1, 1))

        self._overlay_orig = p.plot(
            pen=pg.mkPen(color=COLOR_ORIG, width=1.2), name="Original")
        self._overlay_recon = p.plot(
            pen=pg.mkPen(color=COLOR_RECON, width=1.2), name="Reconstructed")
        self._overlay_orig.setDownsampling(auto=True, method='peak')
        self._overlay_recon.setDownsampling(auto=True, method='peak')
        self._p_overlay = p

        return glw

    # ── 构建 Side-by-side 面板 ────────────────────────────

    def _make_side_panel(self, y_lo: float, y_hi: float) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        font = make_font(9)

        for clr, bg, label_text in [
            (COLOR_ORIG, COLOR_BG, "Original"),
            (COLOR_RECON, COLOR_BG, "Reconstructed")
        ]:
            glw = pg.GraphicsLayoutWidget()
            glw.setBackground(bg)
            p = glw.addPlot()
            p.setLabel('left', 'µV', color=COLOR_TEXT)
            p.setLabel('bottom', 'Time', units='s', color=COLOR_TEXT)
            p.setTitle(label_text, color=COLOR_TEXT, size='10pt')
            for ax_name in ('left', 'bottom'):
                ax = p.getAxis(ax_name)
                ax.setPen(COLOR_GRID)
                ax.setTextPen(COLOR_TEXT)
                ax.setTickFont(font)
            p.showGrid(x=True, y=True, alpha=0.06)
            p.setYRange(y_lo, y_hi, padding=0)
            p.setXRange(0, self._sd.window_sec, padding=0)
            p.hideButtons()
            p.setMouseEnabled(x=False, y=False)
            p.setMenuEnabled(False)

            curve = p.plot(pen=pg.mkPen(color=clr, width=1.0))
            curve.setDownsampling(auto=True, method='peak')
            layout.addWidget(glw)

            if clr == COLOR_ORIG:
                self._side_orig = curve
                self._p_side_left = p
            else:
                self._side_recon = curve
                self._p_side_right = p

        return w

    # ── 模式切换 ──────────────────────────────────────────

    def _toggle_mode(self):
        self._overlay = self._btn_toggle.isChecked()
        self._btn_toggle.setText("Overlay Mode" if self._overlay
                                 else "Side-by-Side")
        self._stack.setCurrentIndex(0 if self._overlay else 1)
        self._tick()

    # ── 范围更新 ──────────────────────────────────────────

    def update_ranges(self):
        """时窗或幅值变化后，更新 X/Y 轴范围。"""
        sd = self._sd
        y_lo, y_hi = sd.y_range_detail(self._ch)
        w = sd.window_sec

        self._p_overlay.setXRange(0, w, padding=0)
        self._p_overlay.setYRange(y_lo, y_hi, padding=0)

        if hasattr(self, '_p_side_left'):
            self._p_side_left.setXRange(0, w, padding=0)
            self._p_side_left.setYRange(y_lo, y_hi, padding=0)
            self._p_side_right.setXRange(0, w, padding=0)
            self._p_side_right.setYRange(y_lo, y_hi, padding=0)

        amp_val = sd.ch_amp[self._ch] if sd.ch_amp is not None else 0.0
        self.setWindowTitle(
            f"Ch{self._ch + 1}  —  Original vs Reconstructed  |  "
            f"Amplitude {amp_val:.1f} µV")

    # ── 帧更新 ────────────────────────────────────────────

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

        orig_slice = sd.orig[self._ch, ptr:ptr + wp]
        recon_slice = sd.recon[self._ch, ptr:ptr + wp]

        # Overlay 模式
        self._overlay_orig.setData(self._t_buf, orig_slice)
        self._overlay_recon.setData(self._t_buf, recon_slice)

        # Side-by-side 模式
        if hasattr(self, '_side_orig'):
            self._side_orig.setData(self._t_buf, orig_slice)
            self._side_recon.setData(self._t_buf, recon_slice)

        # 信息栏
        self._lbl_info.setText(
            f"ptr={ptr}  |  window={sd.window_sec*1000:.0f}ms  |  "
            f"amp={sd.amp_scale:.1f}×  |  speed={self._player.speed_mul:.1f}×")

    # ── 关闭 ──────────────────────────────────────────────

    def closeEvent(self, ev):
        try:
            self._player.frame_ready.disconnect(self._tick)
        except (TypeError, RuntimeError):
            pass
        ev.accept()
