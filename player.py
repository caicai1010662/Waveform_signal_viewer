"""
player.py — 播放引擎

  Player  : 精确 QTimer 驱动播放，80fps 同步信号，帧丢弃保护。
            支持循环模式（Loop / Once），变速播放（0.5× ~ 1.5×）。
            grid / detail 两个视图共用同一个 Player 实例。

  信号流:
    QTimer._tick() → frame_ready(ptr) → 各视图更新 → Player.ack()

  调参入口:
    config.TARGET_FPS      — 目标帧率（默认 80）
    config.PLAYBACK_SPEED  — 基础播放速度
    SPEED_MUL_MIN/MAX      — 变速范围
"""

from pyqtgraph.Qt import QtCore
from config import TARGET_FPS, PLAYBACK_SPEED, SPEED_MUL_MIN, SPEED_MUL_MAX


class Player(QtCore.QObject):
    """定时器驱动播放引擎。

    特性:
      80fps 精确帧率，_pending 锁丢帧保护，循环/单次两种播放模式。

    信号:
        frame_ready(int)   — 每帧发射，携带当前采样点位置（ptr）
        state_changed(bool)— 播放/暂停状态变化
        speed_changed(float)— 速度倍率变化
        loop_changed(bool) — 循环模式变化（True=循环, False=单次）
    """

    # Qt 信号（跨线程安全的发布/订阅机制）
    frame_ready   = QtCore.pyqtSignal(int)
    state_changed = QtCore.pyqtSignal(bool)
    speed_changed = QtCore.pyqtSignal(float)
    loop_changed  = QtCore.pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # ── 播放状态 ──────────────────────────────────────
        self.ptr: int = 0            # 当前播放位置（采样点索引）
        self.s_freq: int = 30000     # 采样率（Hz），加载数据时更新
        self.n_samples: int = 0      # 总采样点数，加载数据时更新
        self.window_pts: int = 0     # 当前时间窗口对应的采样点数

        # ── 用户可调 ──────────────────────────────────────
        self.speed_mul: float = 1.0  # 速度倍率（1.0 = 基础速度）
        self.loop_mode: bool = True  # True = 循环播放, False = 播到末尾暂停

        # ── 内部状态 ──────────────────────────────────────
        self._on = False             # 是否正在播放
        self._pending = False        # 帧丢弃标志（上一帧未处理完时跳过新帧）

        # 精确定时器 — 每 1000/TARGET_FPS 毫秒触发一次 _tick()
        self._timer = QtCore.QTimer(
            timerType=QtCore.Qt.PreciseTimer, timeout=self._tick)

    # ═════════════════════════════════════════════════════════
    # 配置 — 加载数据后调用
    # ═════════════════════════════════════════════════════════

    def configure(self, s_freq: int, n_samples: int, window_pts: int):
        """更新采样率和数据长度（加载新数据时由 app.py 调用）。"""
        self.s_freq = s_freq
        self.n_samples = n_samples
        self.window_pts = window_pts

    # ═════════════════════════════════════════════════════════
    # 播放控制
    # ═════════════════════════════════════════════════════════

    def play(self):
        """开始播放。启动定时器，每帧触发 frame_ready 信号。"""
        if self.n_samples <= 0:
            return
        self._on = True
        self._timer.start(int(1000 / TARGET_FPS))  # 定时器间隔（毫秒）
        self.state_changed.emit(True)

    def pause(self):
        """暂停播放。停止定时器，清除 pending 标志。"""
        self._on = False
        self._timer.stop()
        self._pending = False
        self.state_changed.emit(False)

    def toggle(self):
        """切换播放/暂停。Space 键和 Start 按钮调用此方法。"""
        self.pause() if self._on else self.play()

    def seek(self, pos: int):
        """跳转到指定采样点位置。

        Args:
            pos: 目标采样点索引。自动钳制到有效范围 [0, n_samples - window_pts]。
        """
        bound = max(0, self.n_samples - self.window_pts)
        self.ptr = max(0, min(pos, bound))
        self.frame_ready.emit(self.ptr)  # 立即通知视图更新

    def seek_delta(self, d: int):
        """相对跳转。← → 键调用此方法。

        Args:
            d: 偏移量（可为负）。正=前进，负=后退。
        """
        self.seek(self.ptr + d)

    # ═════════════════════════════════════════════════════════
    # 速度控制
    # ═════════════════════════════════════════════════════════

    def set_speed(self, mul: float):
        """设置速度倍率。受 SPEED_MUL_MIN/MAX 限制。

        Args:
            mul: 速度倍率。1.0 = 基础速度，2.0 = 两倍速。
        """
        self.speed_mul = max(SPEED_MUL_MIN, min(SPEED_MUL_MAX, mul))
        self.speed_changed.emit(self.speed_mul)

    def speed_up(self):
        """加快一档。Ctrl+↑ 键调用。

        档位表与 SPEED_MUL_MIN/MAX 对齐：
        当前 MIN=0.5, MAX=1.5 → 三档 [0.5, 1.0, 1.5]。
        扩大范围时只需同步改此列表。
        """
        for s in [0.5, 1.0, 1.5]:
            if s > self.speed_mul + 0.001:  # 浮点安全余量
                self.set_speed(s)
                return

    def speed_down(self):
        """减慢一档。Ctrl+↓ 键调用。"""
        for s in [1.5, 1.0, 0.5]:
            if s < self.speed_mul - 0.001:
                self.set_speed(s)
                return

    # ═════════════════════════════════════════════════════════
    # 循环控制
    # ═════════════════════════════════════════════════════════

    def toggle_loop(self):
        """切换循环模式。Loop 按钮调用。

        loop_mode=True  → 播到末尾自动跳回开头继续
        loop_mode=False → 播到末尾自动暂停
        """
        self.loop_mode = not self.loop_mode
        self.loop_changed.emit(self.loop_mode)

    # ═════════════════════════════════════════════════════════
    # 内部 — 定时器回调（每帧触发）
    # ═════════════════════════════════════════════════════════

    def _tick(self):
        """定时器每帧回调。

        流程:
          1. 检查 _pending — 上一帧未处理完则跳过（帧丢弃）
          2. 设 _pending = True（防止重入）
          3. 发射 frame_ready(ptr) → 各视图更新
          4. 计算步长，移动 ptr
          5. 到达末尾 → 循环归零 / 暂停
        """
        if self._pending:
            return  # 上一帧还没处理完，丢弃本帧

        self._pending = True
        self.frame_ready.emit(self.ptr)

        # 每帧移动的采样点数
        # = 采样率 × 基础速度 × 速度倍率 / 帧率
        step = max(1, int(self.s_freq * PLAYBACK_SPEED
                          * self.speed_mul / TARGET_FPS))
        self.ptr += step

        # 到达数据末尾
        if self.ptr + self.window_pts >= self.n_samples:
            if self.loop_mode:
                self.ptr = 0           # 循环模式：回到开头
                self._pending = False  # 显式清除（不依赖同步信号副作用）
            else:
                self._pending = False
                self.pause()           # 单次模式：自动暂停

    def ack(self):
        """视图完成帧更新后调用，释放 _pending 锁。

        每个视图的 _on_frame() / scroll() / _tick() 方法
        处理完 frame_ready 信号后必须调用此方法。
        """
        self._pending = False
