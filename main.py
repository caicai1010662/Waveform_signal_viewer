"""
SignalViewer — Original vs Reconstructed Neural Signal Comparison Viewer

  Entry point. Modular architecture:
    config.py        — Parameters, color scheme, stylesheet
    data.py          — File loading + SignalData (memmap support)
    decimator.py     — LTTB + Min-Max downsampling
    player.py        — Playback engine (60fps)
    grid.py          — Grid view (Row + Tile modes)
    detail.py        — Detail window (Overlay + Side-by-side)
    oscilloscope.py  — Oscilloscope scrolling mode
    app.py           — Main window
"""

import sys
from pyqtgraph.Qt import QtWidgets, QtGui
from config import STYLESHEET, FONT_FAMILY, FONT_SIZE
from app import MainWindow

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
