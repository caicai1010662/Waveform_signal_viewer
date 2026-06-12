"""
utils.py — 共享工具函数

  提供字体创建、画笔创建、通道标签格式化。
  所有函数带 LRU 缓存，避免重复创建相同对象。
"""

from functools import lru_cache

from pyqtgraph.Qt import QtGui
import pyqtgraph as pg

from config import FONT_FAMILY, FONT_SIZE


# ═══════════════════════════════════════════════════════════════
# 字体工厂
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=32)
def make_font(size: int = FONT_SIZE, bold: bool = True,
              family: str = FONT_FAMILY) -> QtGui.QFont:
    font = QtGui.QFont(family, size)
    font.setBold(bold)
    return font


# ═══════════════════════════════════════════════════════════════
# 画笔工厂
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=8)
def make_pen(color: str, width: float = 0.6) -> pg.mkPen:
    return pg.mkPen(color=color, width=width)


# ═══════════════════════════════════════════════════════════════
# 通道标签
# ═══════════════════════════════════════════════════════════════

def format_channel_label(ch: int) -> str:
    """0-based 通道索引 → 人类可读标签（Ch1, Ch2, ...）。"""
    return f"Ch{ch + 1}"
