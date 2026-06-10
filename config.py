"""
config.py — SignalViewer 全局调参中心

  所有可调参数、配色、样式表集中于此。
  改完保存 → 重启 python main.py 即可生效。
  VS Code Dark Theme。
"""

import pyqtgraph as pg


# ═══════════════════════════════════════════════════════════════
# 一、显示参数 — 控制波形窗口和渲染
# ═══════════════════════════════════════════════════════════════

# 默认时间窗口（秒）。0.05 = 屏幕上显示 50ms 的数据
# 改大 → 看到更多时间上下文，波形变窄
# 改小 → 看到更细节的波形，波形展开
WINDOW_SEC = 0.05

# 目标帧率。80 = 每秒刷新 80 次
# 低配机可降到 30，高配机可提到 120
TARGET_FPS = 80

# 基础播放速度（数据秒 / 真实秒）。0.005 = 1秒数据需要 200 秒播放完
# 改大 → 默认播放变快，改小 → 默认播放变慢
PLAYBACK_SPEED = 0.005

# 波形线宽（像素）。越大线越粗
# 深色背景下建议 ≥ 1.0，否则波形太纤细看不清
LINE_WIDTH = 1.2


# ═══════════════════════════════════════════════════════════════
# 二、网格布局 — 控制一屏显示多少个通道
# ═══════════════════════════════════════════════════════════════

# Tile 模式（Browse）每行格子数。6 = 一行 6 个通道
# 屏幕小就改小（4），屏幕大就改大（8）
TILE_COLS = 6

# Row 模式（Compare）一屏可见行数。6 = 同时显示 6 个通道
# 改大 → 一屏看到更多通道，但每个通道变窄
# 改小 → 每个通道更宽，但一屏看到的通道变少
# 低配机建议 4~6
VISIBLE_ROWS = 6

# Tile 模式（Browse）一屏可见行数。4 = 同时 4 行 × 6 列 = 24 通道
# 低配机建议 2~3
VISIBLE_TILE_ROWS = 4


# ═══════════════════════════════════════════════════════════════
# 三、性能参数 — 2048 通道流畅渲染的关键
# ═══════════════════════════════════════════════════════════════

# LTTB 降采样目标点数。每个通道数据会被压缩到这个点数再渲染
# 一般设为屏幕宽度（1920）即可，超过这个数人眼也分辨不出
DECIMATION_TARGET = 2560

# MinMax 降采样 bucket 数。Tile 缩略图用的更快速降采样
MINMAX_BUCKETS = 400

# 是否缓存降采样结果。True = 降采样一次后缓存，下次直接用
CACHE_DECIMATED = True


# ═══════════════════════════════════════════════════════════════
# 四、滑动条范围限制 — 用户拖动滑块时的上下限
# ═══════════════════════════════════════════════════════════════

# 时间窗口范围（秒）。用户能缩到的最小/最大时间窗
WINDOW_SEC_MIN = 0.05   # 最小 50ms（最放大）
WINDOW_SEC_MAX = 0.10   # 最大 100ms（最缩小）

# 幅值缩放范围。1.0 = 原始幅值，改大 = 波形纵向拉高
AMP_SCALE_MIN  = 1.0    # 最小 1.0×（波形最扁）
AMP_SCALE_MAX  = 3.0   # 最大 3.0×（波形最拉伸）

# 播放速度倍率范围。1.0 = 基础速度
SPEED_MUL_MIN  = 0.5    # 最慢 0.5×
SPEED_MUL_MAX  = 1.5    # 最快 1.5×


# ═══════════════════════════════════════════════════════════════
# 五、数据驱动参数 — 自动计算通道幅值和间距
# ═══════════════════════════════════════════════════════════════

# 通道幅值估算用的百分位。99.5 = 取绝对值最大的前 0.5% 作为峰值
# 改大（99.9）→ 更保守，少裁切尖峰；改小（95）→ 更多尖峰被裁
Y_PERCENTILE = 99.9

# 通道间距系数。实际间距 = 通道幅值 × SPACING_FACTOR × amp_scale
# 改小（1.0~1.5）→ 通道紧凑，波形填满，更多通道一屏可见
# 改大（3.0~5.0）→ 通道松散，每个通道留白大
SPACING_FACTOR = 3


# ═══════════════════════════════════════════════════════════════
# 六、配色方案 — VS Code Dark Theme
#    改一个颜色就换一种风格，所有用到这个颜色的地方自动跟着变
# ═══════════════════════════════════════════════════════════════

COLOR_BG     = "#181818"  # 窗口底色（最外层背景）
COLOR_CARD   = "#1E1E1E"  # 波形面板底色（比 BG 稍亮一点，形成层级感）
COLOR_ORIG   = "#4FC1FF"  # 原始信号曲线颜色
COLOR_RECON  = "#DCDCAA"  # 重建信号曲线颜色
COLOR_GRID   = "#4A4A4A"  # 零基线 / 辅助参考线（提亮，在斑马纹上清晰可见）
COLOR_ACCENT = "#007ACC"  # 交互强调色（按钮选中、滑块手柄、hover 高亮）
COLOR_TEXT   = "#FFFFFF"  # 所有文字的颜色
COLOR_SEP    = "#3E3E42"  # 中轴分隔线（强化左右面板的切割感）
COLOR_SLIDER = "#464646"  # 滑动条轨道底色（比卡片稍亮，确保轨道可见）
COLOR_HOVER  = "#2A2D2E"  # 鼠标悬停时的底色
COLOR_ZEBRA  = "#222222"  # 斑马纹交替行底色（Row 模式每隔一个通道的浅色背景）


# ═══════════════════════════════════════════════════════════════
# 七、字体 — 全局统一字体和字号
# ═══════════════════════════════════════════════════════════════

FONT_FAMILY = "Microsoft YaHei Mono"  # 主字体。等宽中英文字体
FONT_SIZE   = 16               # 全局字号（窗口标题、标签、状态栏等）
FONT_SIZE_SMALL = 16           # 小字号（按钮文字等）


# ═══════════════════════════════════════════════════════════════
# 八、Qt 样式表 (QSS) — 按钮 / 滑动条 / 滚动条 / 标签的外观
#    语法类似 CSS。{COLOR_XXX} 会被上面第六节的配色自动填充
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

/* ── 普通按钮 (Load / Start / Loop / Compare / Browse / Roll) ── */
QPushButton {{
    background-color: #3C3C3C;   /* 按钮底色 */
    color: #E0E0E0;              /* 按钮文字色 */
    border: 1px solid transparent; /* 边框透明，扁平化 */
    border-radius: 10px;         /* 圆角半径 */
    padding: 10px 20px;          /* 内边距：上下 10px，左右 20px */
    font-size: 20px;             /* 按钮字号 */
    font-weight: bold;           /* 加粗 */
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
/* 滑轨（长条背景） */
QSlider::groove:horizontal {{
    background: {COLOR_SLIDER};  /* 轨道颜色 */
    height: 20px;                /* 轨道高度（粗细） */
    border-radius: 10px;         /* 轨道圆角 */
}}
/* 滑块手柄（可拖动的那个小方块） */
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT};  /* 手柄颜色 = 主题蓝 */
    width: 14px;                 /* 手柄宽度 */
    height: 14px;                /* 手柄高度 */
    margin: -4px 0;              /* 微调垂直居中 */
    border-radius: 7px;          /* 手柄圆角 */
}}
/* 滑块悬停 */
QSlider::handle:horizontal:hover {{
    background: #1194EB;         /* 悬停时主题蓝提亮 */
}}

/* ── 垂直滑动条 (右侧通道浏览 _slider_ch) ── */
/* 滑轨 */
QSlider::groove:vertical {{
    background: {COLOR_SLIDER};  /* 轨道颜色 */
    width: 13px;                 /* 轨道宽度 */
    border-radius: 10px;         /* 轨道圆角 */
}}
/* 滑块手柄 */
QSlider::handle:vertical {{
    background: {COLOR_ACCENT};  /* 手柄颜色 = 主题蓝 */
    height: 35px;                /* 手柄高度（纵向长度） */
    width: 15px;                 /* 手柄宽度 */
    margin: 0 -4px;              /* 微调水平居中 */
    border-radius: 5px;          /* 手柄圆角 */
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
    border: 1px solid {COLOR_SEP};
}}
"""


# ═══════════════════════════════════════════════════════════════
# 九、pyqtgraph 全局绘图配置
# ═══════════════════════════════════════════════════════════════

# 关闭抗锯齿：神经信号波形不需要平滑边缘，关掉省性能
# 关闭 OpenGL：集成显卡用 OpenGL 反而可能更慢
pg.setConfigOptions(antialias=False, useOpenGL=False)

# 波形画布的默认背景色和前景色
pg.setConfigOption('background', COLOR_CARD)   # 画布底色 = 面板色
pg.setConfigOption('foreground', COLOR_TEXT)   # 坐标轴文字色
