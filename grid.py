"""
grid.py — 网格视图（核心渲染模块）

  这是整个项目最复杂、最关键的模块。负责将 2048 通道的神经信号
  高效渲染到屏幕上。

  核心设计:
    1. 对象池 (Object Pool)    — 只创建 VISIBLE_ROWS 条曲线，滚动时复用
    2. 窗口裁剪 (Window Clipping)— 每条曲线只存 window_pts(~1500) 个点
    3. 视口剔除 (Viewport Culling)— 只渲染看得见的通道
    4. 零基线 (Zero Baseline)   — 每个通道画虚线参考线
    5. 斑马纹 (Zebra Striping)  — 交替行背景防止串行

  Row 模式 (Compare): VISIBLE_ROWS 条曲线/侧，一通道一行，垂直堆叠
  Tile 模式 (Browse): VISIBLE_TILE_ROWS × TILE_COLS 个栅格/侧

  调参入口:
    config.VISIBLE_ROWS       — Row 模式可见通道数（低配机 4~6）
    config.VISIBLE_TILE_ROWS  — Tile 模式可见行数
    config.TILE_COLS          — Tile 模式每行格子数
    config.LINE_WIDTH         — 波形线宽
    config.SPACING_FACTOR     — 通道间距系数（影响 Y 偏移）
    MAX_POINTS_PER_CURVE      — 每曲线最大点数（超此则步进取样）
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

# 每曲线最大数据点数。超过此数 → 每隔 N 个取 1 个（简单步进降采样）
# 默认 200ms × 30kHz = 6000 点。一般 window_pts = 1500，远低于上限。
MAX_POINTS_PER_CURVE = 6000


class GridView(QtWidgets.QWidget):
    """网格视图 — 窗口裁剪 + 对象池 + 零线 + 斑马纹。

    信号:
        channel_clicked(int) — 用户点击某通道，发射绝对通道索引

    内部模式:
        "row"  — 一行一通道（Compare 按钮）
        "tile" — 栅格模式（Browse 按钮）
    """

    # Qt 信号
    channel_clicked = QtCore.pyqtSignal(int)

    def __init__(self, sd: SignalData):
        super().__init__()
        self._sd = sd                      # 数据容器引用
        self._mode = "row"                 # 当前模式

        # ── Y 轴偏移（8KB，存所有 2048 通道的 Y 中心位置）──
        self._y_offsets: np.ndarray = None
        self._total_height: float = 0.0    # 所有通道堆叠的总高度

        # ── 视口状态 ──────────────────────────────────────
        self._ch_offset: int = 0           # 当前可见的第一个通道索引
        self._last_ptr: int = -1           # 上次渲染的 ptr（去重用）

        # ── 对象池（只存 VISIBLE_ROWS 个对象，不是 2048 个）─
        self._curves_orig: list[pg.PlotDataItem] = []   # 左侧原始信号曲线
        self._curves_recon: list[pg.PlotDataItem] = []  # 右侧重建信号曲线
        self._labels_l: list[pg.TextItem] = []           # 左侧通道标签
        self._labels_r: list[pg.TextItem] = []           # 右侧通道标签
        self._zero_lines_l: list[pg.InfiniteLine] = []   # 左侧零基线
        self._zero_lines_r: list[pg.InfiniteLine] = []   # 右侧零基线
        self._zebra_rects: list[pg.LinearRegionItem] = [] # 斑马纹交替行

        # ── 时间轴缓冲区（复用，避免每帧分配 numpy 数组）───
        self._t_buf = np.empty(0, dtype=np.float32)

        # ── Tile 模式专用 ─────────────────────────────────
        self._tiles_orig: dict[tuple, tuple] = {}  # (row,col) → (PlotItem, curve)
        self._tiles_recon: dict[tuple, tuple] = {}

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    # UI 框架 — 只执行一次
    #     QStackedLayout 叠加 Row 面板和 Tile 面板
    #     根据 mode 切换显示哪一个
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        """构建双层 UI：Row 面板（索引 0）+ Tile 面板（索引 1）。"""
        root = QtWidgets.QStackedLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Row 模式面板 ─────────────────────────────────
        self._row_widget = QtWidgets.QWidget()
        self._row_widget.setStyleSheet(f"background-color: {COLOR_CARD};")
        row_lay = QtWidgets.QHBoxLayout(self._row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(0)

        # 左侧 PlotWidget — 原始信号
        self._left_pw = pg.PlotWidget(background=COLOR_CARD)
        self._left_pi = self._left_pw.getPlotItem()
        self._left_vb = self._left_pi.getViewBox()
        self._config_plot(self._left_pi)

        # 中间分隔线
        self._sep_v = self._make_vsep()
        self._sep_v.setStyleSheet(
            f"border: none; background-color: {COLOR_SEP};")

        # 右侧 PlotWidget — 重建信号
        self._right_pw = pg.PlotWidget(background=COLOR_CARD)
        self._right_pi = self._right_pw.getPlotItem()
        self._right_vb = self._right_pi.getViewBox()
        self._config_plot(self._right_pi)

        # 左右 Y 轴同步
        self._left_vb.sigYRangeChanged.connect(self._sync_y_range)

        row_lay.addWidget(self._left_pw, 1)
        row_lay.addWidget(self._sep_v)
        row_lay.addWidget(self._right_pw, 1)

        # ── Tile 模式面板 ─────────────────────────────────
        self._tile_widget = QtWidgets.QWidget()
        self._tile_widget.setStyleSheet(f"background-color: {COLOR_CARD};")
        tile_lay = QtWidgets.QHBoxLayout(self._tile_widget)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_lay.setSpacing(0)

        # 左侧栅格 — 原始信号
        self._tile_left = pg.GraphicsLayoutWidget()
        self._tile_left.setBackground(COLOR_CARD)
        # 右侧栅格 — 重建信号
        self._tile_right = pg.GraphicsLayoutWidget()
        self._tile_right.setBackground(COLOR_CARD)

        tile_lay.addWidget(self._tile_left, 1)
        tile_lay.addWidget(self._make_vsep())
        tile_lay.addWidget(self._tile_right, 1)

        root.addWidget(self._row_widget)
        root.addWidget(self._tile_widget)

        # 事件过滤 — 捕获点击（打开 Detail）
        # Row 模式: 监听左右 PlotWidget 的 viewport
        self._left_pw.viewport().installEventFilter(self)
        self._right_pw.viewport().installEventFilter(self)
        # Tile 模式: 监听左右 GraphicsLayoutWidget 的 viewport
        self._tile_left.viewport().installEventFilter(self)
        self._tile_right.viewport().installEventFilter(self)

    @staticmethod
    def _make_vsep():
        """创建垂直分隔线。"""
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setStyleSheet(f"border: none; background-color: {COLOR_SEP};")
        f.setFixedWidth(2)
        return f

    def _config_plot(self, pi: pg.PlotItem):
        """配置 PlotItem：隐藏所有装饰，只显示波形和数据。"""
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
        """切换 "row" ↔ "tile" 模式。重建曲线池并渲染。"""
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
    # 构建 — 创建对象池，仅 VISIBLE_ROWS 个曲线
    # ═══════════════════════════════════════════════════════════

    def build(self):
        """(重)构建整个视图。"""
        self.clear()
        sd = self._sd
        if not sd.ready:
            return

        # 计算全量 Y 偏移（8KB，可忽略）
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)
        self._ch_offset = 0
        self._last_ptr = -1

        if self._mode == "row":
            self._build_row_pool(sd)
        else:
            self._build_tile_pool(sd)

    def _build_row_pool(self, sd: SignalData):
        """Row 模式对象池: VISIBLE_ROWS 条曲线 + 零线 + 斑马纹 + 左右标签。

        关键: 只创建 VISIBLE_ROWS 条曲线（不是 2048 条）。
              滚动时通过 _fill_row_data 换绑数据，不创建新对象。
        """
        n_pool = min(VISIBLE_ROWS, sd.n_chan)
        w = sd.window_sec

        # ── 斑马纹 — 偶数行加浅色背景 ────────────────────
        # 初始值随便设 [0,1]，_fill_row_data 中会用真实 ch_amp 更新
        for i in range(n_pool):
            if i % 2 == 1:
                continue  # 只给偶数行加斑马纹
            zebra = pg.LinearRegionItem(
                values=[0, 1],
                orientation='horizontal',
                brush=pg.mkBrush(COLOR_ZEBRA),
                pen=pg.mkPen(None))           # 无边框
            zebra.setMovable(False)           # 用户不可拖动
            self._left_pi.addItem(zebra)
            self._zebra_rects.append(zebra)

        # ── 曲线 + 零线 + 标签 ────────────────────────────
        for i in range(n_pool):
            abs_ch = i
            offset = float(self._y_offsets[abs_ch])

            # 零基线（虚线）
            dash_pen = pg.mkPen(color=COLOR_GRID, width=0.5,
                                style=QtCore.Qt.DashLine)
            zl = pg.InfiniteLine(pos=offset, angle=0, pen=dash_pen)
            zr = pg.InfiniteLine(pos=offset, angle=0, pen=dash_pen)
            self._left_pi.addItem(zl)
            self._right_pi.addItem(zr)
            self._zero_lines_l.append(zl)
            self._zero_lines_r.append(zr)

            # 信号曲线
            c_l = self._left_pi.plot(pen=make_pen(COLOR_ORIG, LINE_WIDTH))
            c_l.setDownsampling(auto=False)    # 手动控制降采样
            c_l.setSkipFiniteCheck(True)       # 跳过 NaN/Inf 检查（性能优化）
            self._curves_orig.append(c_l)

            c_r = self._right_pi.plot(pen=make_pen(COLOR_RECON, LINE_WIDTH))
            c_r.setDownsampling(auto=False)
            c_r.setSkipFiniteCheck(True)
            self._curves_recon.append(c_r)

            # 标签底色动态匹配：偶数行(斑马纹)用 COLOR_ZEBRA，奇数行用 COLOR_CARD
            bg_color = COLOR_ZEBRA if i % 2 == 0 else COLOR_CARD

            # 左侧标签 — Z 值 100 绝对置顶，波形永远从文字下方穿过
            lbl_l = pg.TextItem("", color=COLOR_TEXT, anchor=(0, 0.5),
                                fill=pg.mkBrush(bg_color))
            lbl_l.setFont(make_font(8))
            lbl_l.setZValue(100)
            self._left_pi.addItem(lbl_l)
            self._labels_l.append(lbl_l)

        # 填充初始数据（含斑马纹真实高度 + 标签位置）
        self._fill_row_data(sd, 0)

        # 设置 X 范围 — 左右各留 2% 呼吸空间，避免波形撞墙
        pad_x = w * 0.02
        self._left_vb.setXRange(-pad_x, w + pad_x, padding=0)
        self._right_vb.setXRange(-pad_x, w + pad_x, padding=0)

        # Y 视口 — 使用真实幅值计算，替代平均行高
        self._update_row_yrange(sd)

    def _build_tile_pool(self, sd: SignalData):
        """Tile 模式: 创建栅格网格。

        每个 tile 是一个独立的 PlotItem（含零线）。
        GraphicsLayoutWidget 自动管理行列布局。
        """
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
                y_lo, y_hi = -ch_amp * 1.2, ch_amp * 1.2  # Y 范围: ±幅值×1.2

                # 左侧 tile
                pi_l = self._tile_left.addPlot(row=r, col=c)
                self._config_tile_plot(pi_l, abs_ch, font, y_lo, y_hi)
                _add_tile_zero_line(pi_l, y_lo, y_hi)
                c_l = pi_l.plot(pen=make_pen(COLOR_ORIG, 0.4))
                c_l.setDownsampling(auto=False)
                c_l.setSkipFiniteCheck(True)
                self._tiles_orig[(r, c)] = (pi_l, c_l)

                # 右侧 tile
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
        """配置单个 Tile 的 PlotItem。"""
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
        """清空所有曲线、标签、零线、斑马纹、tile。

        在模式切换和 rebuild 时调用。
        """
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
    # 数据填充 — 热路径，每次滚动/每帧播放都调用
    #    从 memmap 读取当前窗口数据 → setData 到曲线
    #    同时更新零线位置、标签位置、斑马纹位置
    # ═══════════════════════════════════════════════════════════

    def _fill_row_data(self, sd: SignalData, ptr: int):
        """Row 模式核心渲染: 从 memmap 读取可见通道的当前窗口数据。

        Args:
            sd:  数据容器
            ptr: 当前播放位置（采样点索引）

        性能: 16 条曲线 × 1500 点 = 24k floats ≈ 96KB。极轻量。
        """
        wp = sd.window_pts               # 窗口采样点数 (~1500)
        if ptr + wp > sd.n_samples:      # 边界保护
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)   # memmap 切片（不复制数据）
        # 时间轴缓冲区 — 只在 wp 变化时重新分配（避免每帧分配 1500 个 float）
        if len(self._t_buf) != wp:
            self._t_buf = np.arange(wp, dtype=np.float32) / sd.s_freq
        t = self._t_buf
        t, wp = _step_decimate(t, wp)   # 超限时步进降采样

        n_pool = len(self._curves_orig)

        for i in range(n_pool):
            abs_ch = self._ch_offset + i  # 绝对通道索引
            active = abs_ch < sd.n_chan

            if active:
                offset = float(self._y_offsets[abs_ch])
                # 从 memmap 读当前通道 + 当前窗口的数据
                self._curves_orig[i].setData(
                    t, sd.orig[abs_ch, t_slice][:wp] + offset)
                self._curves_recon[i].setData(
                    t, sd.recon[abs_ch, t_slice][:wp] + offset)
                # 当前通道的真实高度（基于 ch_amp，不是平均行高）
                ch_h = float(sd.ch_amp[abs_ch]) * SPACING_FACTOR * sd.amp_scale
            else:
                offset = 0.0
                ch_h = 1.0

            vis = active
            self._curves_orig[i].setVisible(vis)
            self._curves_recon[i].setVisible(vis)

            # 更新零线位置
            if i < len(self._zero_lines_l):
                self._zero_lines_l[i].setPos(offset)
                self._zero_lines_l[i].setVisible(vis)
            if i < len(self._zero_lines_r):
                self._zero_lines_r[i].setPos(offset)
                self._zero_lines_r[i].setVisible(vis)

            # 更新标签 — 动态 X 边距（窗口宽度的 1%），告别贴边窒息感
            lbl_text = format_channel_label(abs_ch) if active else ""
            x_margin = sd.window_sec * 0.01
            if i < len(self._labels_l):
                self._labels_l[i].setText(lbl_text)
                self._labels_l[i].setPos(x_margin, offset)

            # 更新斑马纹（仅偶数行）— 使用真实通道高度 ch_h 完美包裹
            zi = i // 2
            if i % 2 == 0 and zi < len(self._zebra_rects):
                if active:
                    rgn = self._zebra_rects[zi]
                    rgn.setRegion([offset - ch_h / 2.0, offset + ch_h / 2.0])
                    rgn.setVisible(True)
                else:
                    self._zebra_rects[zi].setVisible(False)

    def _fill_tile_data(self, sd: SignalData, ptr: int):
        """Tile 模式核心渲染: 更新所有可见栅格的数据。"""
        wp = sd.window_pts
        if ptr + wp > sd.n_samples:
            ptr = max(0, sd.n_samples - wp)
        t_slice = slice(ptr, ptr + wp)
        # 时间轴缓冲区 — 复用 row 模式的 _t_buf
        if len(self._t_buf) != wp:
            self._t_buf = np.arange(wp, dtype=np.float32) / sd.s_freq
        t = self._t_buf
        t, wp = _step_decimate(t, wp)

        # 更新左侧栅格
        for (r, c), (pi, curve) in list(self._tiles_orig.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch >= sd.n_chan:
                continue
            curve.setData(t, sd.orig[abs_ch, t_slice][:wp])
            _update_tile_label(pi, abs_ch)

        # 更新右侧栅格
        for (r, c), (pi, curve) in list(self._tiles_recon.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch >= sd.n_chan:
                continue
            curve.setData(t, sd.recon[abs_ch, t_slice][:wp])

    # ═══════════════════════════════════════════════════════════
    # 视口同步 — 左右 ViewBox Y 轴联动
    # ═══════════════════════════════════════════════════════════

    def _sync_y_range(self, vb, range_):
        """左侧 Y 范围变化 → 同步到右侧。blockSignals 防止递归。"""
        try:
            self._right_vb.blockSignals(True)
            self._right_vb.setYRange(*range_, padding=0)
        finally:
            self._right_vb.blockSignals(False)

    # ═══════════════════════════════════════════════════════════
    # 外部接口（由 app.py 调用）
    # ═══════════════════════════════════════════════════════════

    def scroll(self, ptr: int, sd: SignalData):
        """播放时每帧调用。更新可见通道的窗口数据。

        ptr 去重优化: 如果 ptr 没变就跳过（避免重复渲染同一帧）。
        """
        if ptr == self._last_ptr:
            return
        self._last_ptr = ptr

        if self._mode == "row":
            self._fill_row_data(sd, ptr)
        else:
            self._fill_tile_data(sd, ptr)

    def set_offset(self, sd: SignalData, val: int):
        """通道滑动条回调。更新可见通道范围 + Y 视口。

        Args:
            val: 滑动条值（第一个可见通道的索引）
        """
        if not sd.ready:
            return
        val = max(0, min(val, sd.max_channel_offset))
        if val == self._ch_offset:
            return  # 无变化，跳过
        self._ch_offset = val

        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            self._update_row_yrange(sd)
        else:
            self._update_tile_yranges(sd)
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def update_ranges(self, sd: SignalData):
        """时窗变化回调。更新 X 范围 + 重填数据。"""
        w = sd.window_sec
        if self._mode == "row":
            pad_x = w * 0.02
            self._left_vb.setXRange(-pad_x, w + pad_x, padding=0)
            self._right_vb.setXRange(-pad_x, w + pad_x, padding=0)
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
        else:
            for pi, _ in list(self._tiles_orig.values()):
                pi.setXRange(0, w, padding=0)
            for pi, _ in list(self._tiles_recon.values()):
                pi.setXRange(0, w, padding=0)
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def reload_amp(self, sd: SignalData):
        """幅值变化回调。重算 Y 偏移 + 更新数据 + Y 视口。"""
        if not sd.ready:
            return
        self._y_offsets = sd.y_offsets_all()
        self._total_height = float(sd.total_y_height)

        if self._mode == "row":
            self._fill_row_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)
            self._update_row_yrange(sd)
        else:
            self._update_tile_yranges(sd)
            self._fill_tile_data(sd, self._last_ptr if self._last_ptr >= 0 else 0)

    def _update_tile_yranges(self, sd: SignalData):
        """更新所有 Tile 的 Y 轴范围 — 仅在通道切换 / 幅值变化时调用。

        播放期间（_fill_tile_data）不再调用 setYRange，减少 ViewBox 重计算开销。
        """
        for (r, c), (pi, _) in list(self._tiles_orig.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch < sd.n_chan:
                ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
                pi.setYRange(-ch_amp * 1.2, ch_amp * 1.2, padding=0)
        for (r, c), (pi, _) in list(self._tiles_recon.items()):
            abs_ch = self._ch_offset + r * TILE_COLS + c
            if abs_ch < sd.n_chan:
                ch_amp = float(sd.ch_amp[abs_ch]) * sd.amp_scale
                pi.setYRange(-ch_amp * 1.2, ch_amp * 1.2, padding=0)

    def _update_row_yrange(self, sd: SignalData):
        """基于当前可见通道的真实幅值计算 Y 轴视口范围。

        摒弃平均行高（total_height/n_chan），改用首尾通道的实际 ch_amp。
        解决通道幅值差异大时视口漂移、波形"挤作一团"的 Bug。
        """
        n_pool = len(self._curves_orig)
        if n_pool == 0 or not sd.ready or self._y_offsets is None:
            return

        top_ch = self._ch_offset
        bot_ch = min(sd.n_chan - 1, self._ch_offset + n_pool - 1)

        top_h = float(sd.ch_amp[top_ch]) * SPACING_FACTOR * sd.amp_scale
        bot_h = float(sd.ch_amp[bot_ch]) * SPACING_FACTOR * sd.amp_scale

        y_top = self._y_offsets[top_ch] + top_h / 2.0
        y_bot = self._y_offsets[bot_ch] - bot_h / 2.0

        # 上下各留 5% 的呼吸空间，防止波峰/波谷贴边
        pad = (y_top - y_bot) * 0.05
        self._left_vb.setYRange(y_bot - pad, y_top + pad, padding=0)
        self._right_vb.setYRange(y_bot - pad, y_top + pad, padding=0)

    # ═══════════════════════════════════════════════════════════
    # 事件过滤 — 点击（打开 Detail）
    # ═══════════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        """捕获鼠标左键点击 → 确定被点击的通道 → 发射 channel_clicked 信号。

        Row 模式: 通过 Y 坐标找最接近的通道（基于 _y_offsets）。
        Tile 模式: 遍历所有栅格，通过 ViewBox 的 sceneBoundingRect 定位。
        """
        if not self._sd.ready or self._y_offsets is None:
            return False

        if (event.type() == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton):

            # ── Row 模式 ──────────────────────────────
            if self._mode == "row":
                pw = (self._left_pw
                      if obj == self._left_pw.viewport()
                      else self._right_pw)
                vb = pw.getPlotItem().getViewBox()
                data_pt = vb.mapToView(pg.Point(event.pos()))
                y = float(data_pt.y())
                # 找 Y 坐标最接近的通道
                ch = int(np.argmin(np.abs(self._y_offsets - y)))
                if 0 <= ch < self._sd.n_chan:
                    self.channel_clicked.emit(ch)
                return True

            # ── Tile 模式 ─────────────────────────────
            elif self._mode == "tile":
                # 确定点击来源: 左侧还是右侧栅格
                if obj == self._tile_left.viewport():
                    glw = self._tile_left
                    tiles = self._tiles_orig
                elif obj == self._tile_right.viewport():
                    glw = self._tile_right
                    tiles = self._tiles_recon
                else:
                    return False

                # 将 viewport 坐标转为 scene 坐标
                scene_pt = glw.mapToScene(event.pos())
                for (r, c), (pi, _) in tiles.items():
                    vb = pi.getViewBox()
                    if vb.sceneBoundingRect().contains(scene_pt):
                        abs_ch = self._ch_offset + r * TILE_COLS + c
                        if 0 <= abs_ch < self._sd.n_chan:
                            self.channel_clicked.emit(abs_ch)
                        return True

        return False


# ═══════════════════════════════════════════════════════════════
# 模块级工具函数
# ═══════════════════════════════════════════════════════════════

def _step_decimate(t: np.ndarray, wp: int) -> tuple[np.ndarray, int]:
    """简单步进降采样。当数据点数超过 MAX_POINTS_PER_CURVE 时，每隔 N 个取 1 个。

    Args:
        t:  时间轴数组
        wp: 原始数据点数

    Returns:
        (降采样后的 t, 降采样后的 wp)

    注意: 正常情况 window_pts ≈ 1500 < MAX_POINTS_PER_CURVE(6000)，
          所以这个函数通常不做任何裁剪，直接返回原值。
    """
    if wp > MAX_POINTS_PER_CURVE:
        step = wp // MAX_POINTS_PER_CURVE + 1
        return t[::step], len(t[::step])
    return t, wp


def _update_tile_label(pi: pg.PlotItem, ch: int):
    """更新 Tile 的通道标签文本（用于滚动时换绑通道）。"""
    for item in pi.items:
        if isinstance(item, pg.TextItem):
            item.setText(format_channel_label(ch))
            break


def _add_tile_zero_line(pi: pg.PlotItem, y_lo: float, y_hi: float):
    """在 Tile 的 PlotItem 中添加 Y=0 的虚线参考线。"""
    line = pg.InfiniteLine(pos=0, angle=0,
                            pen=pg.mkPen(color=COLOR_GRID, width=0.5,
                                         style=QtCore.Qt.DashLine))
    pi.addItem(line)
