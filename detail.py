"""
detail.py — 单通道详情弹出窗口

  DetailWindow : 点击通道后弹出的放大视图。
                 默认 Overlay 模式（原始+重建叠在同一轴），
                 可切换 Side-by-side 模式（左右并排）。
                 播放时每帧 setData，连接 Player.frame_ready。

  调参入口: 本模块顶部的常量，改完保存 → 重启即可生效。
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from config import (COLOR_BG, COLOR_ORIG, COLOR_RECON, COLOR_GRID,
                     COLOR_TEXT, COLOR_CARD, FONT_FAMILY)
from data import SignalData
from player import Player
from utils import make_font


# ═══════════════════════════════════════════════════════════════
# 模块参数 — 调这里，不用去 config.py
# ═══════════════════════════════════════════════════════════════

# 字体字号
DETAIL_FONT_TICK  = 15        # 坐标轴刻度数字
DETAIL_FONT_LABEL = 50        # 坐标轴标题（µV / Time）、图例文字
DETAIL_FONT_TITLE = 12        # Side-by-side 面板标题（Rawdata / Recdata）

# 视觉
DETAIL_GRID_ALPHA = 0.9       # 网格虚线透明度
DETAIL_LINE_WIDTH = 1.5       # 波形线宽（像素）
DETAIL_Y_PADDING  = 1.0       # Y 轴上下留白系数（改大=波形上下空余更多）
DETAIL_X_PADDING  = 0.02      # X 轴左右呼吸空间（比例，0 = 贴边）

# 按钮
DETAIL_BTN_HEIGHT = 35        # 顶栏切换按钮高度（像素）
DETAIL_BTN_FONT   = 19        # 顶栏切换按钮字号

# 窗口偏移（相对于主窗口）
DETAIL_OFFSET_X = 30
DETAIL_OFFSET_Y = 30


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

        # ── Y 轴范围 — 分信号源计算，解决幅值差异导致的削顶 ──
        # Overlay: 取两信号中较大的范围，确保双方完整可见
        y_lo_overlay, y_hi_overlay = sd.y_range_overlay(ch, DETAIL_Y_PADDING)
        # Side-by-side: 各自用自己的幅值
        y_lo_orig, y_hi_orig = sd.y_range_detail(ch, 'orig', DETAIL_Y_PADDING)
        y_lo_recon, y_hi_recon = sd.y_range_detail(ch, 'recon', DETAIL_Y_PADDING)

        amp_orig = sd.ch_amp[ch] if sd.ch_amp is not None else 0.0
        amp_recon = sd.ch_amp_recon[ch] if sd.ch_amp_recon is not None else 0.0
        self.setWindowTitle(
            f"Ch{ch + 1}  —  Rawdata {amp_orig:.1f}µV  |  Recdata {amp_recon:.1f}µV")
        self.resize(1200, 420)

        # ── 构建 UI ──────────────────────────────────────
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)

        main_v = QtWidgets.QVBoxLayout(cw)
        main_v.setContentsMargins(4, 25, 4, 15)
        main_v.setSpacing(4)

        # 顶栏: 模式切换按钮（紧凑，不抢波形空间）
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(2, 0, 2, 0)

        self._btn_toggle = QtWidgets.QPushButton("Overlay")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.setChecked(True)
        self._btn_toggle.setFixedHeight(DETAIL_BTN_HEIGHT)
        self._btn_toggle.setStyleSheet(
            f"font-size: {DETAIL_BTN_FONT}px; padding: 2px 10px; "
            "font-weight: bold;")
        self._btn_toggle.clicked.connect(self._toggle_mode)

        top.addStretch(1)
        top.addWidget(self._btn_toggle)
        top.addStretch(1)
        main_v.addLayout(top)

        # 波形区域: QStackedLayout 叠加两个面板
        self._stack = QtWidgets.QStackedLayout()
        main_v.addLayout(self._stack, 1)

        self._overlay_panel = self._make_overlay_panel(y_lo_overlay, y_hi_overlay)
        self._stack.addWidget(self._overlay_panel)

        self._side_panel = self._make_side_panel(y_lo_orig, y_hi_orig,
                                                 y_lo_recon, y_hi_recon)
        self._stack.addWidget(self._side_panel)

        # 连接到播放器，立即显示第一帧
        self._t_buf = np.empty(0, dtype=np.float32)  # 时间轴缓冲区（复用，避免每帧分配）
        player.frame_ready.connect(self._tick)
        self._tick()

    # ═════════════════════════════════════════════════════
    # Overlay 面板 — 两条曲线在同一轴
    # ═════════════════════════════════════════════════════

    @staticmethod
    def _force_axis_font(ax, tick_font: QtGui.QFont):
        """暴力设置坐标轴刻度字体。

        pyqtgraph 的 setTickFont() 在某些版本/场景下不生效，
        此方法遍历轴的子 QGraphicsTextItem 直接设字体兜底。
        轴标题（LabelItem）走 HTML 渲染，由 _setup_axes() 通过
        p.setLabel() 的 size/family/bold 参数设置，不在这里处理。
        """
        ax.setTickFont(tick_font)
        for child in ax.childItems():
            if isinstance(child, QtWidgets.QGraphicsTextItem):
                child.setFont(tick_font)

    def _setup_axes(self, p: pg.PlotItem):
        """统一配置坐标轴样式：标题字体、刻度字体、网格、禁用交互。"""
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

    def _make_overlay_panel(self, y_lo: float, y_hi: float) -> pg.GraphicsLayoutWidget:
        """构建叠加模式面板: 一个 PlotItem + 两条曲线 + 图例。"""
        glw = pg.GraphicsLayoutWidget()
        glw.setBackground(COLOR_BG)
        p = glw.addPlot()

        self._setup_axes(p)
        p.setYRange(y_lo, y_hi, padding=0)
        p.setXRange(0, self._sd.window_sec, padding=DETAIL_X_PADDING)

        legend = p.addLegend(offset=(1, 1))
        legend.mouseDragEvent = lambda ev: None  # 锁定图例不可拖拽
        font_size_str = f'{DETAIL_FONT_LABEL}pt'
        for _, label in legend.items:
            label.setText(label.text, family=FONT_FAMILY, size=font_size_str, bold=True)

        self._overlay_orig = p.plot(
            pen=pg.mkPen(color=COLOR_ORIG, width=DETAIL_LINE_WIDTH), name="Rawdata")
        self._overlay_recon = p.plot(
            pen=pg.mkPen(color=COLOR_RECON, width=DETAIL_LINE_WIDTH), name="Recdata")

        # 关闭自动降采样 — Detail 窗口数据量小（~1500 点），
        # method='peak' 会把高频噪声涂抹成实心色块，反而失真
        self._overlay_orig.setDownsampling(auto=False)
        self._overlay_recon.setDownsampling(auto=False)
        self._p_overlay = p

        return glw

    # ═════════════════════════════════════════════════════
    # Side-by-side 面板 — 左右并排两个独立 PlotItem
    # ═════════════════════════════════════════════════════

    def _make_side_panel(self,
                         y_lo_orig: float, y_hi_orig: float,
                         y_lo_recon: float, y_hi_recon: float) -> QtWidgets.QWidget:
        """构建并排模式面板: 左侧 Rawdata + 右侧 Recdata，各自独立 Y 范围。"""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        font_title = make_font(DETAIL_FONT_TITLE)

        for clr, bg, label_text, y_lo, y_hi in [
            (COLOR_ORIG, COLOR_BG, "Rawdata", y_lo_orig, y_hi_orig),
            (COLOR_RECON, COLOR_BG, "Recdata", y_lo_recon, y_hi_recon),
        ]:
            glw = pg.GraphicsLayoutWidget()
            glw.setBackground(bg)
            p = glw.addPlot()
            p.setTitle(label_text, color=COLOR_TEXT)
            if hasattr(p, 'titleLabel') and p.titleLabel is not None:
                p.titleLabel.setFont(font_title)

            self._setup_axes(p)
            # 各自独立 Y 范围 — Rawdata 和 Recdata 用各自的 ch_amp
            p.setYRange(y_lo, y_hi, padding=0)
            p.setXRange(0, self._sd.window_sec, padding=DETAIL_X_PADDING)

            curve = p.plot(pen=pg.mkPen(color=clr, width=DETAIL_LINE_WIDTH))
            curve.setDownsampling(auto=False)
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
        """切换 Overlay ↔ Side by Side 显示模式。"""
        self._overlay = not self._overlay
        self._btn_toggle.setChecked(True)  # 始终 checked，表示"当前选中模式"
        self._btn_toggle.setText("Overlay" if self._overlay else "Side by Side")
        self._stack.setCurrentIndex(0 if self._overlay else 1)
        self._tick()

    # ═════════════════════════════════════════════════════
    # 范围更新 — 主窗口滑动条改变时调用
    # ═════════════════════════════════════════════════════

    def update_ranges(self):
        """时窗或幅值变化后，同步更新 X/Y 轴范围和窗口标题。"""
        sd = self._sd
        w = sd.window_sec

        # Overlay: 取两信号较大的范围
        y_lo_overlay, y_hi_overlay = sd.y_range_overlay(self._ch, DETAIL_Y_PADDING)
        self._p_overlay.setXRange(0, w, padding=DETAIL_X_PADDING)
        self._p_overlay.setYRange(y_lo_overlay, y_hi_overlay, padding=0)

        # Side-by-side: 各自用自己的幅值
        if hasattr(self, '_p_side_left'):
            y_lo_orig, y_hi_orig = sd.y_range_detail(self._ch, 'orig', DETAIL_Y_PADDING)
            y_lo_recon, y_hi_recon = sd.y_range_detail(self._ch, 'recon', DETAIL_Y_PADDING)
            self._p_side_left.setXRange(0, w, padding=DETAIL_X_PADDING)
            self._p_side_left.setYRange(y_lo_orig, y_hi_orig, padding=0)
            self._p_side_right.setXRange(0, w, padding=DETAIL_X_PADDING)
            self._p_side_right.setYRange(y_lo_recon, y_hi_recon, padding=0)

        amp_orig = sd.ch_amp[self._ch] if sd.ch_amp is not None else 0.0
        amp_recon = sd.ch_amp_recon[self._ch] if sd.ch_amp_recon is not None else 0.0
        self.setWindowTitle(
            f"Ch{self._ch + 1}  —  Rawdata {amp_orig:.1f}µV  |  Recdata {amp_recon:.1f}µV")

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
