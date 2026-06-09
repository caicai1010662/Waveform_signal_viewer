"""
config.py — 全局参数、配色、样式表

  SignalViewer 所有可调参数集中于此。
  极简工业风 (Minimalist Industrial Style)。
"""

import pyqtgraph as pg

# ── 显示参数 ──────────────────────────────────────────────
WINDOW_SEC = 0.05
TARGET_FPS = 60
PLAYBACK_SPEED = 0.005
LINE_WIDTH = 0.6

# ── 网格布局 ──────────────────────────────────────────────
TILE_COLS = 6                 # Tile 模式每行栅格数
VISIBLE_ROWS = 8              # Row 模式一屏可见行数
VISIBLE_TILE_ROWS = 4         # Tile 模式一屏可见行数

# ── 2048 通道性能 ─────────────────────────────────────────
DECIMATION_TARGET = 1500      # LTTB 降采样目标点数（匹配屏宽）
MINMAX_BUCKETS = 400          # MinMax 降采样 bucket 数（tile 模式）
CACHE_DECIMATED = True        # 是否缓存降采样结果

# ── 范围限制 ──────────────────────────────────────────────
WINDOW_SEC_MIN = 0.01
WINDOW_SEC_MAX = 0.20
AMP_SCALE_MIN  = 0.2
AMP_SCALE_MAX  = 5.0
SPEED_MUL_MIN  = 0.1
SPEED_MUL_MAX  = 10.0

# ── 数据驱动参数 ──────────────────────────────────────────
Y_PERCENTILE   = 99.5
SPACING_FACTOR = 3.2

# ── 配色 — 极简工业风 ─────────────────────────────────────
COLOR_BG       = "#0A0A0A"   # 画布底色 — 极致深黑
COLOR_ORIG     = "#FFFFFF"   # 原始信号 — 纯白
COLOR_RECON    = "#FFD600"   # 重建信号 — 亮黄
COLOR_GRID     = "#262626"   # 辅助线/刻度 — 极暗灰
COLOR_ACCENT   = "#FF4500"   # 交互/Hover/选中 — 橙红
COLOR_TEXT     = "#A0A0A0"   # 文字 — 中性灰
COLOR_CARD     = "#0F0F12"   # 卡片/面板底色
COLOR_SEP      = "#1F1F24"   # 分隔线
COLOR_SLIDER   = "#2A2A30"   # 滑动条底色
COLOR_HOVER    = "#353540"   # 按钮悬停

# ── 字体 ──────────────────────────────────────────────────
FONT_FAMILY = "Times New Roman"
FONT_SIZE   = 11
FONT_SIZE_SMALL = 9

# ── 样式表 ────────────────────────────────────────────────
STYLESHEET = f"""
QWidget {{
    background-color: {COLOR_BG}; color: {COLOR_TEXT};
    font-family: "{FONT_FAMILY}"; font-size: {FONT_SIZE}px; font-weight: 400;
}}

/* ── 按钮 ─────────────────────────────────────────── */
QPushButton {{
    background: {COLOR_CARD}; color: {COLOR_TEXT};
    border: 1px solid {COLOR_SEP}; border-radius: 6px;
    padding: 6px 16px; font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE}px;
}}
QPushButton:hover {{
    border-color: {COLOR_HOVER}; background: #1A1A20;
    color: {COLOR_ORIG};
}}
QPushButton:pressed {{
    background: {COLOR_BG}; border-color: {COLOR_ACCENT};
}}
QPushButton:disabled {{
    color: #3A3A40; border-color: #1A1A20; background: #0D0D10;
}}
QPushButton:checked {{
    border-color: {COLOR_ACCENT}; color: {COLOR_ORIG};
    background: #1C1C22;
}}

/* ── 滑动条 ───────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {COLOR_SLIDER}; height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT}; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{
    background: #FF6A30;
}}
QSlider::groove:vertical {{
    background: {COLOR_SLIDER}; width: 4px; border-radius: 2px;
}}
QSlider::handle:vertical {{
    background: {COLOR_ACCENT}; height: 12px; width: 12px;
    margin: 0 -4px; border-radius: 6px;
}}
QSlider::handle:vertical:hover {{
    background: #FF6A30;
}}

/* ── 滚动条 ───────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #3A3A44; border-radius: 3px; min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: #505060; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── 标签 ─────────────────────────────────────────── */
QLabel {{
    color: {COLOR_TEXT}; background-color: transparent;
    font-family: "{FONT_FAMILY}"; font-size: {FONT_SIZE}px;
}}

/* ── 进度对话框 ────────────────────────────────────── */
QProgressDialog {{
    background: {COLOR_CARD}; border: 1px solid {COLOR_SEP};
    border-radius: 8px;
}}
QProgressDialog QLabel {{
    color: {COLOR_TEXT}; font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE}px;
}}

/* ── 消息框 ───────────────────────────────────────── */
QMessageBox {{
    background: {COLOR_CARD}; border: 1px solid {COLOR_SEP};
}}
QMessageBox QLabel {{
    color: {COLOR_TEXT}; font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE}px;
}}
"""

# ── pyqtgraph 全局配置 ────────────────────────────────────
pg.setConfigOptions(antialias=True, useOpenGL=False)
pg.setConfigOption('background', COLOR_BG)
pg.setConfigOption('foreground', COLOR_GRID)
