"""
detail.py — 单通道详情弹出窗口

  DetailWindow : 点击通道后弹出的放大视图。
                 默认 Overlay 模式（原始+重建叠在同一轴），
                 可切换 Side-by-side 模式（左右并排）。
                 播放时每帧 setData，连接 Player.frame_ready。

  调参入口: 无。YT范围从 SignalData.y_range_detail() 获取。
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_BG, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_CARD, FONT_FAMILY)
from data import SignalData
from player import Player
from utils import make_font


class DetailWindow(QtWidgets.QMainWindow):
    """单通道原始 vs 重建详情对比窗口。

    两种显示模式:
      Overlay    — 两条曲线叠在同一 PlotItem 中（有图例区分）
      Side-by-side — 左右两个 PlotItem 并排

    生命周期:
      点击通道 → new DetailWindow → show → 跟随播放更新 → 关闭窗口 → disconnect
    """

    def __init__(self, ch: int, sd: SignalData, player: Player, parent=None):
        super().__init__(parent)
        self._ch = ch                     # 通道索引（0-based）
        self._sd = sd                     # 数据容器
        self._player = player             # 播放引擎
        self._overlay = True              # 当前模式（True=叠加, False=并排）

        # 窗口标题: ChX — 幅值
        y_lo, y_hi = sd.y_range_detail(ch)
        amp_val = sd.ch_amp[ch] if sd.ch_amp is not None else 0.0
        self.setWindowTitle(
            f"Ch{ch + 1}  —  Original vs Reconstructed  |  "
            f"Amplitude {amp_val:.1f} µV")
        self.resize(1200, 420)

        # ── 构建 UI ──────────────────────────────────────
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)

        main_v = QtWidgets.QVBoxLayout(cw)
        main_v.setContentsMargins(4, 4, 4, 4)
        main_v.setSpacing(4)

        # 顶栏: 模式切换按钮 + 信息标签
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

        # 波形区域: QStackedLayout 叠加两个面板
        self._stack = QtWidgets.QStackedLayout()
        main_v.addLayout(self._stack, 1)

        self._overlay_panel = self._make_overlay_panel(y_lo, y_hi)
        self._stack.addWidget(self._overlay_panel)

        self._side_panel = self._make_side_panel(y_lo, y_hi)
        self._stack.addWidget(self._side_panel)

        # 连接到播放器，立即显示第一帧
        self._t_buf = np.empty(0, dtype=np.float32)  # 时间轴缓冲区（复用，避免每帧分配）
        player.frame_ready.connect(self._tick)
        self._tick()

    # ═════════════════════════════════════════════════════
    # Overlay 面板 — 两条曲线在同一轴
    # ═════════════════════════════════════════════════════

    def _make_overlay_panel(self, y_lo: float, y_hi: float) -> pg.GraphicsLayoutWidget:
        """构建叠加模式面板: 一个 PlotItem + 两条曲线 + 图例。"""
        glw = pg.GraphicsLayoutWidget()
        glw.setBackground(COLOR_BG)
        p = glw.addPlot()

        # 坐标轴标签
        p.setLabel('left', 'µV', color=COLOR_TEXT)
        p.setLabel('bottom', 'Time', units='s', color=COLOR_TEXT)
        for ax_name in ('left', 'bottom'):
            ax = p.getAxis(ax_name)
            ax.setPen(COLOR_GRID)
            ax.setTextPen(COLOR_TEXT)
            ax.setTickFont(make_font(9))

        p.showGrid(x=True, y=True, alpha=0.06)  # 半透明网格
        p.setYRange(y_lo, y_hi, padding=0)
        p.setXRange(0, self._sd.window_sec, padding=0)
        p.hideButtons()
        p.setMouseEnabled(x=False, y=False)
        p.setMenuEnabled(False)

        # 图例（右上角）
        p.addLegend(offset=(1, 1))

        # 原始信号曲线（白/蓝）+ 重建信号曲线（黄）
        self._overlay_orig = p.plot(
            pen=pg.mkPen(color=COLOR_ORIG, width=1.2), name="Original")
        self._overlay_recon = p.plot(
            pen=pg.mkPen(color=COLOR_RECON, width=1.2), name="Reconstructed")

        # 开启 pyqtgraph 自动降采样（渲染时根据屏幕像素自动压缩）
        self._overlay_orig.setDownsampling(auto=True, method='peak')
        self._overlay_recon.setDownsampling(auto=True, method='peak')
        self._p_overlay = p

        return glw

    # ═════════════════════════════════════════════════════
    # Side-by-side 面板 — 左右并排两个独立 PlotItem
    # ═════════════════════════════════════════════════════

    def _make_side_panel(self, y_lo: float, y_hi: float) -> QtWidgets.QWidget:
        """构建并排模式面板: 两个 GraphicsLayoutWidget 左右排列。"""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        font = make_font(9)

        for clr, bg, label_text in [
            (COLOR_ORIG, COLOR_BG, "Original"),        # 左: 原始
            (COLOR_RECON, COLOR_BG, "Reconstructed")   # 右: 重建
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

    # ═════════════════════════════════════════════════════
    # 模式切换
    # ═════════════════════════════════════════════════════

    def _toggle_mode(self):
        """切换 Overlay ↔ Side-by-side 显示模式。"""
        self._overlay = self._btn_toggle.isChecked()
        self._btn_toggle.setText("Overlay Mode" if self._overlay
                                 else "Side-by-Side")
        self._stack.setCurrentIndex(0 if self._overlay else 1)
        self._tick()  # 立即刷新显示

    # ═════════════════════════════════════════════════════
    # 范围更新 — 主窗口滑动条改变时调用
    # ═════════════════════════════════════════════════════

    def update_ranges(self):
        """时窗或幅值变化后，同步更新 X/Y 轴范围和窗口标题。"""
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

    # ═════════════════════════════════════════════════════
    # 帧更新 — 播放时每秒触发 TARGET_FPS 次
    # ═════════════════════════════════════════════════════

    def _tick(self):
        """播放器每帧回调。从 memmap 读取当前窗口数据，setData 到曲线。

        优化: _t_buf 只分配一次，后续复用（避免每帧分配 numpy 数组）。
        """
        sd = self._sd
        if not sd.ready:
            return
        ptr = self._player.ptr
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            return

        # 时间轴缓冲区（只分配一次）
        if len(self._t_buf) != wp:
            self._t_buf = np.arange(wp, dtype=np.float32) / sd.s_freq

        # 从 memmap 读取当前通道的当前窗口
        orig_slice = sd.orig[self._ch, ptr:ptr + wp]
        recon_slice = sd.recon[self._ch, ptr:ptr + wp]

        # 仅更新当前可见模式的曲线（隐藏面板的 setData 纯属浪费）
        if self._overlay:
            self._overlay_orig.setData(self._t_buf, orig_slice)
            self._overlay_recon.setData(self._t_buf, recon_slice)
        else:
            if hasattr(self, '_side_orig'):
                self._side_orig.setData(self._t_buf, orig_slice)
                self._side_recon.setData(self._t_buf, recon_slice)

        # 底部信息栏
        self._lbl_info.setText(
            f"ptr={ptr}  |  window={sd.window_sec*1000:.0f}ms  |  "
            f"amp={sd.amp_scale:.1f}×  |  speed={self._player.speed_mul:.1f}×")

    # ═════════════════════════════════════════════════════
    # 关闭
    # ═════════════════════════════════════════════════════

    def closeEvent(self, ev):
        """窗口关闭时断开播放器连接，防止信号发到已销毁的窗口。"""
        try:
            self._player.frame_ready.disconnect(self._tick)
        except (TypeError, RuntimeError):
            pass
        ev.accept()
