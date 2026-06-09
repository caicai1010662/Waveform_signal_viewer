"""
utils.py — 共享工具

  make_font()           : Times New Roman 字体工厂（带缓存）
  make_pen()            : pyqtgraph 画笔工厂（带缓存）
  format_channel_label(): 通道标签格式化
"""

from functools import lru_cache

from pyqtgraph.Qt import QtGui
import pyqtgraph as pg

from config import FONT_FAMILY, FONT_SIZE, FONT_SIZE_SMALL


@lru_cache(maxsize=32)
def make_font(size: int = FONT_SIZE, weight: int = 400) -> QtGui.QFont:
    """创建 Times New Roman 字体。"""
    font = QtGui.QFont(FONT_FAMILY, size)
    font.setWeight(weight)
    return font


@lru_cache(maxsize=128)
def make_pen(color: str, width: float = 0.6) -> pg.mkPen:
    """创建 pyqtgraph 画笔。"""
    return pg.mkPen(color=color, width=width)


def format_channel_label(ch: int) -> str:
    """格式化通道标签，例如: "Ch1", "Ch42"。"""
    return f"Ch{ch + 1}"


def make_fixed_label(text: str, font_size: int = FONT_SIZE_SMALL,
                     color: str = "#A0A0A0") -> pg.TextItem:
    """创建固定文本标签（用于通道编号等）。"""
    from config import COLOR_TEXT
    c = color if color else COLOR_TEXT
    label = pg.TextItem(text, color=c, anchor=(0, 0.5))
    label.setFont(make_font(font_size))
    return label
