"""
config.py — 全局参数、配色、样式表

  SignalViewer 所有可调参数集中于此。
  VS Code Dark Theme。
"""

import pyqtgraph as pg

# ── 显示参数 ──────────────────────────────────────────────
WINDOW_SEC = 0.05
TARGET_FPS = 60
PLAYBACK_SPEED = 0.005
LINE_WIDTH = 1.2  # VS Code 深色背景下，高亮色需要更粗的线条支撑

# ── 网格布局 ──────────────────────────────────────────────
TILE_COLS = 6                 # Tile 模式每行栅格数
VISIBLE_ROWS = 6              # Row 模式一屏可见行数
VISIBLE_TILE_ROWS = 4         # Tile 模式一屏可见行数

# ── 2048 通道性能 ─────────────────────────────────────────
DECIMATION_TARGET = 1500      # LTTB 降采样目标点数（匹配屏宽）
MINMAX_BUCKETS = 400          # MinMax 降采样 bucket 数（tile 模式）
CACHE_DECIMATED = True        # 是否缓存降采样结果

# ── 范围限制 ──────────────────────────────────────────────
WINDOW_SEC_MIN = 0.05
WINDOW_SEC_MAX = 0.10
AMP_SCALE_MIN  = 1.0
AMP_SCALE_MAX  = 10.0
SPEED_MUL_MIN  = 0.5
SPEED_MUL_MAX  = 1.5

# ── 数据驱动参数 ──────────────────────────────────────────
Y_PERCENTILE   = 99.5         # 过滤极端毛刺，让主体波形更饱满
SPACING_FACTOR = 1.5          # 缩小通道留白，波形填满屏幕

# ── 配色 — VS Code Dark Theme ─────────────────────────────
COLOR_BG         = "#181818"  # 画布底色：VS Code 外层背景 (如侧边栏/底栏)
COLOR_CARD       = "#1E1E1E"  # 波形面板：VS Code 核心编辑器底色
COLOR_ORIG       = "#4FC1FF"  # 原始信号：VS Code 变量浅蓝 (极佳的护眼高亮)
COLOR_RECON      = "#DCDCAA"  # 重建信号：VS Code 函数淡黄 (温和且具有对比度)
COLOR_GRID       = "#333333"  # 辅助线/刻度：VS Code 编辑器参考线颜色
COLOR_ACCENT     = "#007ACC"  # 交互/选中：VS Code 标志性主题蓝
COLOR_TEXT       = "#CCCCCC"  # 文字/标签：提高亮度，更清晰
COLOR_SEP        = "#2B2B2B"  # 分隔线：极其细微的面板分割
COLOR_SLIDER     = "#464646"  # 滑动条底色：提亮轨道，与背景拉开层次
COLOR_HOVER      = "#2A2D2E"  # 悬停反馈：VS Code 列表悬停色
COLOR_ZEBRA      = "#222222"  # 斑马纹交替行：比面板色稍微深/亮一点点

# ── 字体 ──────────────────────────────────────────────────
FONT_FAMILY = "Consolas"
FONT_SIZE   = 16
FONT_SIZE_SMALL = 13

# ── 样式表 (VS Code 扁平化风格) ───────────────────────────
STYLESHEET = f"""
QWidget {{
    background-color: {COLOR_BG}; color: {COLOR_TEXT};
    font-family: "{FONT_FAMILY}", "Microsoft YaHei Mono";
    font-size: {FONT_SIZE}px; font-weight: 400;
}}

/* ── 按钮 ───────────────────────── */
QPushButton {{
    background-color: #3C3C3C;
    color: #E0E0E0;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 20px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #464646;  /* 悬停微亮 */
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background-color: #2D2D2D;
}}
QPushButton:disabled {{
    background-color: #252526;  /* 略高于纯黑背景，确保按钮存在物理轮廓 */
    color: #808080;             /* VS Code 标准禁用灰 */
    border: 1px solid #3E3E42;  /* 微弱的边框，拒绝消失在虚空中 */
}}
/* 独立 Toggle 按钮 (如 Loop) 的激活状态 — VS Code 主题蓝 */
QPushButton:checked {{
    background-color: {COLOR_ACCENT};
    color: #FFFFFF;
    border: 1px solid {COLOR_ACCENT};
}}

/* ── 滑动条 ───────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {COLOR_SLIDER}; height: 6px; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT}; width: 14px; height: 14px;
    margin: -4px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: #1194EB; /* 主题蓝提亮 */
}}
QSlider::groove:vertical {{
    background: {COLOR_SLIDER}; width: 4px; border-radius: 2px;
}}
QSlider::handle:vertical {{
    background: {COLOR_ACCENT}; height: 14px; width: 14px;
    margin: 0 -4px; border-radius: 7px;
}}
QSlider::handle:vertical:hover {{
    background: #1194EB;
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

/* ── 其他面板保持纯粹扁平 ───────────────────────────── */
QLabel {{
    background-color: transparent;
}}
QProgressDialog, QMessageBox {{
    background: {COLOR_CARD};
    border: 1px solid {COLOR_SEP};
}}
"""

# ── pyqtgraph 全局配置 ────────────────────────────────────
pg.setConfigOptions(antialias=False, useOpenGL=False)
pg.setConfigOption('background', COLOR_CARD)
pg.setConfigOption('foreground', COLOR_TEXT)
