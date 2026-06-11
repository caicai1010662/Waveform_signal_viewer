"""
utils.py — 共享工具函数

  提供字体创建、画笔创建、通道标签格式化等通用工具。
  所有函数带 LRU 缓存，避免重复创建相同对象。

  调参入口: 无。这些函数本身不含可调参数，它们从 config.py 读取字体/颜色。
"""

from functools import lru_cache

from pyqtgraph.Qt import QtGui
import pyqtgraph as pg

from config import FONT_FAMILY, FONT_SIZE, FONT_SIZE_SMALL


# ═══════════════════════════════════════════════════════════════
# 字体工厂 — 创建 QFont 对象，带 LRU 缓存
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=32)
def make_font(size: int = FONT_SIZE, bold: bool = True,
              family: str = FONT_FAMILY) -> QtGui.QFont:
    """创建字体对象。默认加粗，使用 Microsoft YaHei Mono。

    Args:
        size:   字号。默认从 config.FONT_SIZE 读取（16px）
        bold:   True=加粗（默认）, False=正常
        family: 字体名。默认 FONT_FAMILY。显式纳入缓存键，
                防止更换字体后缓存仍返回旧字体。

    用法:
        font = make_font(12)                     # 12px 加粗
        font = make_font(14, False)              # 14px 正常
        font = make_font(10, family="Consolas")  # 指定其他字体
    """
    font = QtGui.QFont(family, size)
    font.setBold(bold)
    return font


# ═══════════════════════════════════════════════════════════════
# 画笔工厂 — 创建 pyqtgraph 画笔，带 LRU 缓存
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=128)
def make_pen(color: str, width: float = 0.6) -> pg.mkPen:
    """创建 pyqtgraph 画笔对象。

    Args:
        color: 颜色，如 "#4FC1FF" 或 config.COLOR_ORIG
        width: 线宽（像素）。默认 0.6，信号线通常用 1.0~1.5

    用法:
        pen = make_pen("#FFFFFF", 1.2)   # 白色 1.2px 线
    """
    return pg.mkPen(color=color, width=width)


# ═══════════════════════════════════════════════════════════════
# 通道标签格式化
# ═══════════════════════════════════════════════════════════════

def format_channel_label(ch: int) -> str:
    """将 0-based 通道索引转为人类可读标签。

    Args:
        ch: 通道索引，0 = 第 1 个通道

    Returns:
        "Ch1", "Ch2", ..., "Ch2048"
    """
    return f"Ch{ch + 1}"


# ═══════════════════════════════════════════════════════════════
# 固定文本标签（用于通道编号等静态文字）
# ═══════════════════════════════════════════════════════════════

def make_fixed_label(text: str, font_size: int = FONT_SIZE_SMALL,
                     bold: bool = True,
                     color: str = "#FFFFFF") -> pg.TextItem:
    """在波形图上创建固定位置的文本标签。

    Args:
        text:      显示的文本
        font_size: 字号
        bold:      True=加粗（默认）, False=正常
        color:     文字颜色

    返回:
        pg.TextItem 对象，可用 setPos(x, y) 定位
    """
    from config import COLOR_TEXT
    c = color if color else COLOR_TEXT
    label = pg.TextItem(text, color=c, anchor=(0, 0.5))  # 左侧垂直居中锚点
    label.setFont(make_font(font_size, bold))
    return label
