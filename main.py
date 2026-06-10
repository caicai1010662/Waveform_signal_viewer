"""
main.py — SignalViewer 程序入口

  这是整个程序的启动文件。双击或用 python main.py 运行。
  只做一件事：创建 Qt 应用程序 → 加载样式表 → 显示主窗口。

  架构：10 个 .py 文件，无循环依赖，每个模块可独立理解和修改。

  启动流程:
    main.py → QApplication → STYLESHEET → MainWindow → show → 进入事件循环

  依赖链:
    config → data → player → grid/oscilloscope/detail → app → main
"""

import sys
from pyqtgraph.Qt import QtWidgets, QtGui
from config import STYLESHEET, FONT_FAMILY, FONT_SIZE  # 全局样式表、字体
from app import MainWindow                              # 主窗口

if __name__ == '__main__':
    # 1. 创建 Qt 应用程序
    app = QtWidgets.QApplication(sys.argv)

    # 2. 设置全局默认字体（所有控件继承，加粗）
    font = QtGui.QFont(FONT_FAMILY, FONT_SIZE)
    font.setBold(True)
    app.setFont(font)

    # 3. Fusion 风格 — 跨平台一致的现代扁平外观
    app.setStyle('Fusion')

    # 4. 加载 VS Code Dark Theme 样式表（来自 config.py）
    app.setStyleSheet(STYLESHEET)

    # 5. 创建并显示主窗口
    win = MainWindow()
    win.show()

    # 6. 进入 Qt 事件循环（程序在此处等待用户操作）
    sys.exit(app.exec_())
