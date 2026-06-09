"""
player.py — 播放引擎

  Player  : 精确定时器驱动，帧丢弃保护，末尾自动暂停。
           60fps 同步信号，示波器/网格/详情窗共用。
"""

from pyqtgraph.Qt import QtCore
from config import TARGET_FPS, PLAYBACK_SPEED, SPEED_MUL_MIN, SPEED_MUL_MAX


class Player(QtCore.QObject):
    """定时器驱动播放引擎。

    信号:
        frame_ready(int)  — 当前 ptr，每帧触发
        state_changed(bool) — 播放状态变化
        speed_changed(float) — 速度倍率变化
    """

    frame_ready = QtCore.pyqtSignal(int)
    state_changed = QtCore.pyqtSignal(bool)
    speed_changed = QtCore.pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.ptr: int = 0
        self.s_freq: int = 30000
        self.n_samples: int = 0
        self.window_pts: int = 0
        self.speed_mul: float = 1.0
        self._on = False
        self._pending = False
        self._timer = QtCore.QTimer(
            timerType=QtCore.Qt.PreciseTimer, timeout=self._tick)

    # ── 配置 ──────────────────────────────────────────────

    def configure(self, s_freq: int, n_samples: int, window_pts: int):
        self.s_freq = s_freq
        self.n_samples = n_samples
        self.window_pts = window_pts

    # ── 控制 ──────────────────────────────────────────────

    def play(self):
        if self.n_samples <= 0:
            return
        self._on = True
        self._timer.start(int(1000 / TARGET_FPS))
        self.state_changed.emit(True)

    def pause(self):
        self._on = False
        self._timer.stop()
        self._pending = False
        self.state_changed.emit(False)

    def toggle(self):
        self.pause() if self._on else self.play()

    def seek(self, pos: int):
        bound = max(0, self.n_samples - self.window_pts)
        self.ptr = max(0, min(pos, bound))
        self.frame_ready.emit(self.ptr)

    def seek_delta(self, d: int):
        self.seek(self.ptr + d)

    # ── 速度 ──────────────────────────────────────────────

    def set_speed(self, mul: float):
        self.speed_mul = max(SPEED_MUL_MIN, min(SPEED_MUL_MAX, mul))
        self.speed_changed.emit(self.speed_mul)

    def speed_up(self):
        for s in [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 10.0]:
            if s > self.speed_mul:
                self.set_speed(s)
                return

    def speed_down(self):
        for s in [10.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25, 0.1]:
            if s < self.speed_mul:
                self.set_speed(s)
                return

    # ── 内部 ──────────────────────────────────────────────

    def _tick(self):
        if self._pending:
            return
        self._pending = True
        self.frame_ready.emit(self.ptr)
        step = max(1, int(self.s_freq * PLAYBACK_SPEED
                          * self.speed_mul / TARGET_FPS))
        self.ptr += step
        if self.ptr + self.window_pts >= self.n_samples:
            self._pending = False
            self.pause()

    def ack(self):
        self._pending = False
