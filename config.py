"""
config.py — SignalViewer 全局配置

  颜色、字体、QSS 样式表、窗口启动参数。
  模块专属参数已移到各 .py 顶部，对应关系:

    data.py   → WINDOW_SEC, Y_PERCENTILE, SPACING_FACTOR, 滑动条范围
    player.py → TARGET_FPS, PLAYBACK_SPEED, 速度范围
    grid.py   → TILE_COLS, VISIBLE_ROWS, LINE_WIDTH
    detail.py → DETAIL_FONT_*, DETAIL_Y_PADDING, 按钮参数, 窗口偏移

  VS Code Dark Theme。
"""

import pyqtgraph as pg


# ═══════════════════════════════════════════════════════════════
# 启动参数 — 窗口大小、位置、状态
# ═══════════════════════════════════════════════════════════════

WIN_WIDTH  = 1920      # 窗口初始宽度（像素）
WIN_HEIGHT = 1080      # 窗口初始高度（像素）
WIN_X = -1             # 窗口 X 位置：-1=自动居中， 0=贴屏幕左边， 960=主屏右半边
WIN_Y = -1             # 窗口 Y 位置：-1=自动居中， 0=贴屏幕顶端， 100=距顶 100px
WIN_MAXIMIZED = False  # True = 启动后自动最大化，覆盖 WIN_WIDTH/HEIGHT
WIN_TITLE = "SignalViewer"  # 窗口标题


# ═══════════════════════════════════════════════════════════════
# 配色方案 — VS Code Dark Theme
# ═══════════════════════════════════════════════════════════════

COLOR_BG     = "#181818"  # 窗口底色（最外层背景）
COLOR_CARD   = "#1E1E1E"  # 波形面板底色（比 BG 稍亮一点，形成层级感）
COLOR_SIGNAL = "#DCDCAA"  # 信号曲线颜色
COLOR_GRID   = "#4A4A4A"  # Detail 窗坐标轴刻度线颜色
COLOR_ACCENT = "#007ACC"  # 交互强调色（按钮选中、滑块手柄、hover 高亮）
COLOR_TEXT   = "#FFFFFF"  # 所有文字的颜色
COLOR_SLIDER = "#464646"  # 滑动条轨道底色（比卡片稍亮，确保轨道可见）
COLOR_HOVER  = "#2A2D2E"  # 鼠标悬停时的底色
COLOR_ZEBRA  = "#2A2A2A"  # 斑马纹交替行底色（Row 模式每隔一个通道的浅色背景）


# ═══════════════════════════════════════════════════════════════
# 字体 — 全局统一字体和字号
# ═══════════════════════════════════════════════════════════════

FONT_FAMILY = "Microsoft YaHei Mono"  # 主字体。等宽中英文字体
FONT_SIZE   = 18              # 全局字号

# ════════════════════════════════════════
# Qt 样式表 (QSS) — 按钮 / 滑动条 / 滚动条 / 标签的外观
# {COLOR_XXX} 会被上方配色自动填充
# ═══════════════════════════════════════════════════════════════

STYLESHEET = f"""
/* ── 全局默认 ───────────────────────────── */
QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: "{FONT_FAMILY}", "Consolas", monospace;
    font-size: {FONT_SIZE}px;
    font-weight: bold;
}}

/* ── 普通按钮 (Load / Start / Loop / Compare / Browse) ── */
QPushButton {{
    background-color: #3C3C3C;
    color: #E0E0E0;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 20px;
    font-weight: bold;
}}
/* 鼠标悬停 */
QPushButton:hover {{
    background-color: #464646;   /* 悬停底色微亮 */
    color: #FFFFFF;              /* 悬停文字纯白 */
}}
/* 鼠标按下 */
QPushButton:pressed {{
    background-color: #2D2D2D;   /* 按下更深，制造"按下去"的反馈 */
}}
/* 按钮禁用（如数据没加载完时 Load Recdata 不可点） */
QPushButton:disabled {{
    background-color: #252526;   /* 禁用底色 */
    color: #808080;              /* 禁用文字灰 */
    border: 1px solid #3E3E42;   /* 禁用时加微弱边框，避免"消失" */
}}
/* Toggle 按钮选中（如 Loop 按下时 / 模式按钮选中时） */
QPushButton:checked {{
    background-color: {COLOR_ACCENT};  /* 选中底色 = 主题蓝 */
    color: #FFFFFF;                    /* 选中文字白 */
    border: 1px solid {COLOR_ACCENT};  /* 选中边框同色 */
}}

/* ── 水平滑动条 (顶部 Time / Amp / Speed) ── */
/* 滑轨 */
QSlider::groove:horizontal {{
    background: {COLOR_SLIDER};
    height: 16px;
    border-radius: 4px;
}}
/* 手柄 */
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT};
    width: 16px;
    height: 16px;
    margin: -1px 0;
    border-radius: 4px;
}}
/* 滑块悬停 */
QSlider::handle:horizontal:hover {{
    background: #1194EB;         /* 悬停时主题蓝提亮 */
}}

/* ── 垂直滑动条 (右侧通道浏览 _slider_ch) ── */
/* 滑轨 */
QSlider::groove:vertical {{
    background: transparent;
    width: 10px;
    border-radius: 3px;
}}
/* 手柄 */
QSlider::handle:vertical {{
    background: #464646;
    height: 40px;
    width: 8px;
    margin: 0 1px;
    border-radius: 4px;
}}
QSlider::handle:vertical:hover {{
    background: #5A5A5A;
}}
QSlider::handle:vertical:pressed {{
    background: {COLOR_ACCENT};
}}
/* 滑块悬停 */
QSlider::handle:vertical:hover {{
    background: #1194EB;         /* 悬停时主题蓝提亮 */
}}

/* ── 滚动条 (波形区域内部可能出现的滚动条) ── */
QScrollBar:vertical {{
    background: transparent;     /* 滚动条背景透明 */
    width: 6px;                  /* 滚动条宽度 */
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #3A3A44;         /* 滚动条手柄色 */
    border-radius: 3px;
    min-height: 40px;            /* 最小高度，防止太短点不到 */
}}
QScrollBar::handle:vertical:hover {{ background: #505060; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── 标签和其他面板 ── */
QLabel {{
    background-color: transparent; /* 标签背景透明，不遮挡波形 */
}}
QProgressDialog, QMessageBox {{
    background: {COLOR_CARD};
    border: 1px solid #3E3E42;
}}
"""


# ═══════════════════════════════════════════════════════════════
# pyqtgraph 全局绘图配置
# ═══════════════════════════════════════════════════════════════

# 关闭抗锯齿：神经信号波形不需要平滑边缘，关掉省性能
# 关闭 OpenGL：集成显卡用 OpenGL 反而可能更慢
pg.setConfigOptions(antialias=False, useOpenGL=False)

# 波形画布的默认背景色和前景色
pg.setConfigOption('background', COLOR_CARD)   # 画布底色 = 面板色
pg.setConfigOption('foreground', COLOR_TEXT)   # 坐标轴文字色
