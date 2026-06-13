"""
data.py — 数据加载 + SignalData 容器

  负责:
    1. 从 .mat 文件加载 2048 通道神经信号数据
    2. 自动建立 .rawcache 缓存（memmap），二次加载零 RAM 占用
    3. 异步加载（QThread），不阻塞 UI
    4. SignalData 容器：存储原始/重建数据，自动计算每通道幅值、Y 偏移

  调参入口: 本模块顶部的常量，改完保存 → 重启即可生效。
"""

import os
import warnings
from dataclasses import dataclass
from typing import Optional

import numpy as np
import scipy.io as sio
import h5py

from pyqtgraph.Qt import QtCore


# ═══════════════════════════════════════════════════════════════
# 模块参数 — 调这里，不用去 config.py
# ═══════════════════════════════════════════════════════════════

# 默认时间窗口（秒）。0.05 = 屏幕上显示 50ms 的数据
WINDOW_SEC = 0.05

# 时间窗口滑动条范围（秒）
WINDOW_SEC_MIN = 0.05   # 最小 50ms
WINDOW_SEC_MAX = 0.10   # 最大 100ms

# 幅值缩放滑动条范围。1.0 = 原始幅值
AMP_SCALE_MIN = 1.0      # 最小 1.0×
AMP_SCALE_MAX = 3.0      # 最大 3.0×

# 通道幅值估算用的百分位。99.9 = 取绝对值最大的前 0.5% 作为峰值
Y_PERCENTILE = 99.9

# 通道间距系数。实际间距 = 通道幅值 × SPACING_FACTOR × amp_scale
SPACING_FACTOR = 3

# 仅压制 scipy/h5py 的已知 Future/Deprecation 警告，不影响其他模块
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)


# ═══════════════════════════════════════════════════════════════
# 1. Raw 缓存机制 — 将 .mat 提取为 flat float32，后续用 memmap 访问
#    设计目的: 2048ch × 30kHz × N秒 = 海量数据，不能全加载到 RAM
#    .mat (scipy load) → numpy array → .raw 文件 → np.memmap
# ═══════════════════════════════════════════════════════════════

def _raw_cache_path(mat_path: str) -> str:
    """返回 .raw 缓存文件路径。例如 data.mat → data.mat.rawcache"""
    return mat_path + '.rawcache'


def _has_raw_cache(mat_path: str) -> bool:
    """检查是否已有有效 .raw 缓存（且比源 .mat 新）。"""
    raw = _raw_cache_path(mat_path)
    if not os.path.exists(raw):
        return False
    return os.path.getmtime(raw) >= os.path.getmtime(mat_path)


def _write_raw_cache(mat_path: str, data: np.ndarray):
    """将 numpy 数组写入 .raw 缓存文件（flat float32 二进制）。

    先写临时文件，再原子重命名，防止写入中断导致缓存损坏。
    """
    raw_path = _raw_cache_path(mat_path)
    tmp = raw_path + '.tmp'
    data.astype(np.float32).tofile(tmp)
    os.replace(tmp, raw_path)


def _open_memmap(mat_path: str, shape: tuple, dtype=np.float32) -> np.ndarray:
    """以只读 memmap 模式打开 .raw 缓存文件。

    memmap = 硬盘上的数据直接映射到 numpy 数组，不占用 RAM。
    访问 arr[ch, start:end] 时只读取需要的那一小段。
    """
    raw_path = _raw_cache_path(mat_path)
    return np.memmap(raw_path, dtype=dtype, mode='r', shape=shape)


# ═══════════════════════════════════════════════════════════════
# 2. 采样率检测 — .mat 文件中采样率可能叫不同的名字
# ═══════════════════════════════════════════════════════════════

# 常见的采样率字段名列表
SFREQ_KEYS = ['s_freq', 'fs', 'Fs', 'sampling_rate',
              'samplerate', 'sample_rate', 'freq']


def _extract_s_freq(container, get_item) -> int:
    """从 mat dict 或 h5py File 中查找采样率。

    遍历 SFREQ_KEYS，用 get_item 适配 dict[key] 和 h5py[key][()] 的差异。
    """
    for key in SFREQ_KEYS:
        try:
            val = get_item(container, key)
            v = np.array(val).ravel()
            if v.size > 0:
                return int(v[0])
        except Exception:
            continue
    return 30000


# ═══════════════════════════════════════════════════════════════
# 3. 同步加载 — 在 LoaderWorker 线程中调用
# ═══════════════════════════════════════════════════════════════

def _load_mat_sync(path: str, report=None) -> tuple[np.ndarray, int, str]:
    """同步加载 .mat 文件 (v5/v7/v7.3)。

    加载策略:
      1. 先检查是否有 .raw 缓存 → 有则直接 memmap，秒开
      2. 无缓存 → scipy/h5py 加载 → 提取数据 → 写入 .raw 缓存 → memmap
      3. 下次再加载同一文件 → 直接从 .raw memmap（零 RAM 占用）

    Args:
        path:   .mat 文件路径
        report: 进度回调函数，接收字符串消息

    Returns:
        (data_array, s_freq, raw_cache_path)
        data_array 是 numpy 数组或 memmap，形状 (n_chan, n_samples)
    """
    def _r(msg):
        if report:
            report(msg)

    # ── 步骤 1: 尝试 .raw 缓存 ────────────────────────────
    if _has_raw_cache(path):
        _r("正在校验缓存...")
        try:
            # 用 scipy 读元信息（shape + s_freq），验证缓存与源文件一致
            mat = sio.loadmat(path)
            keys = [k for k in mat if not k.startswith('__')]
            best_key = max(keys, key=lambda k: np.size(mat[k]))
            arr = mat[best_key]
            s_freq = _extract_s_freq(mat, lambda c, k: c[k])
            shape = arr.shape
            del mat, arr  # 释放 scipy 数据
            # ── 文件大小校验：同名替换可能导致时间戳不变但内容变了 ──
            raw_path = _raw_cache_path(path)
            expected = shape[0] * shape[1] * 4  # float32
            if os.path.getsize(raw_path) != expected:
                _r("缓存校验失败（大小不匹配），删除缓存，重新加载...")
                os.remove(raw_path)
                raise ValueError("cache size mismatch")
            _r("正在使用缓存...")
            data = _open_memmap(path, shape)
            return data, s_freq, raw_path
        except (NotImplementedError, Exception):
            pass  # 缓存读取失败 → 回退到全量加载

    try:
        # ── 步骤 2a: v5 / v7 格式（scipy.io.loadmat）──────
        _r("正在识别文件格式...")
        mat = sio.loadmat(path)
        keys = [k for k in mat if not k.startswith('__')]   # 过滤 __header__ 等元数据
        if not keys:
            raise ValueError("未找到有效矩阵变量")

        # 取最大的变量作为数据矩阵
        best_key = max(keys, key=lambda k: np.size(mat[k]))
        _r(f"正在读取数据 ({best_key})...")
        arr = mat[best_key]

        # 确保 float32（节省内存，GPU 友好）
        if arr.dtype == np.float32:
            data = arr.copy()
        else:
            data = arr.astype(np.float32, copy=False)

        _r("正在查找采样率...")
        s_freq = _extract_s_freq(mat, lambda c, k: c[k])
        del mat  # 释放原始字典

    except NotImplementedError:
        # ── 步骤 2b: v7.3 格式（h5py）─────────────────────
        _r("正在打开 HDF5 文件...")
        with h5py.File(path, 'r') as f:
            datasets = []

            def _collect(name, obj):
                if isinstance(obj, h5py.Dataset):
                    datasets.append((name, obj))

            f.visititems(_collect)
            valid = [(n, o) for n, o in datasets if '#' not in n]  # 过滤 HDF5 引用
            if not valid:
                raise ValueError("未找到有效矩阵变量")

            best_name, best_ds = max(valid, key=lambda x: x[1].size)
            _r(f"正在读取数据 ({best_name})...")
            data = np.array(best_ds, dtype=np.float32)

            _r("正在查找采样率...")
            s_freq = _extract_s_freq(f, lambda c, k: c[k][()])

    # ── 步骤 3: 数据校验 ─────────────────────────────────
    _r("正在校验数据...")
    if data.ndim != 2:
        raise ValueError(f"数据维度异常: {data.ndim}D (需要 2D: 通道 × 采样点)")

    # ── 步骤 4: 建立 .raw 缓存（供下次快速加载）───────
    _r("正在建立缓存...")
    try:
        _write_raw_cache(path, data)
        raw_path = _raw_cache_path(path)
        memmap_data = _open_memmap(path, data.shape)
        return memmap_data, s_freq, raw_path
    except Exception:
        raw_path = ""

    return data, s_freq, raw_path


# ═══════════════════════════════════════════════════════════════
# 4. LoaderWorker — 异步加载（QThread）
#    在后台线程中运行 _load_mat_sync，通过信号报告进度和结果
#    UI 主线程完全不阻塞，进度对话框实时更新
# ═══════════════════════════════════════════════════════════════

class LoaderWorker(QtCore.QThread):
    """异步加载 .mat 文件。

    信号:
        progress(str)  — 进度消息（"正在识别文件格式..."、"正在读取数据..."）
        finished(ndarray, int, str) — 加载完成 (data, s_freq, cache_path)
        error_msg(str) — 加载失败时发射错误信息
    """

    progress  = QtCore.pyqtSignal(str)
    finished  = QtCore.pyqtSignal(np.ndarray, int, str)
    error_msg = QtCore.pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        """QThread 入口。在后台线程中执行。"""
        try:
            data, s_freq, raw_path = _load_mat_sync(self.path, self._report)
            self.progress.emit("加载完成")
            self.finished.emit(data, s_freq, raw_path)
        except Exception as e:
            self.error_msg.emit(str(e))

    def _report(self, msg: str):
        """进度回调 → 通过 Qt 信号发送到主线程。"""
        self.progress.emit(msg)


# ═══════════════════════════════════════════════════════════════
# 5. SignalData — 数据容器
#    持有原始 + 重建信号，所有显示参数由数据统计特性自动计算。
#    用户通过滑动条调整 window_sec / amp_scale，参数自动钳制。
# ═══════════════════════════════════════════════════════════════

@dataclass
class SignalData:
    """单信号数据容器，所有显示参数由数据驱动。

    使用 memmap 存储：首次加载后写入 .raw 缓存，后续零 RAM 占用。
    """

    # ── 数据 ────────────────────────────────────────────
    recon: Optional[np.ndarray] = None   # 信号 (n_chan, n_samples) float32
    recon_path: str = ""

    # ── 元信息 ──────────────────────────────────────────
    s_freq: int = 30000                  # 采样率（Hz）
    n_chan: int = 0                      # 通道总数
    n_samples: int = 0                   # 总采样点数
    window_pts: int = 0                  # 当前时窗对应的采样点数 (= window_sec × s_freq)

    # ── 用户可调参数 ────────────────────────────────────
    window_sec: float = WINDOW_SEC       # 时间窗口（秒），通过 Time 滑动条调整
    amp_scale: float = 1.0               # 幅值缩放倍率，通过 Amp 滑动条调整

    # ── 数据计算参数（compute_params() 后填充）─────────
    ch_amp: Optional[np.ndarray] = None  # (n_chan,) 每通道幅值 (µV)

    # ── 状态属性 ────────────────────────────────────────

    @property
    def ready(self) -> bool:
        """数据是否已加载。"""
        return self.recon is not None

    def max_channel_offset(self, per_page: int = 1) -> int:
        """滑块最大值，保证最后一页始终满屏 per_page 个通道。

        Args:
            per_page: 当前模式一屏的通道数（Trace=VISIBLE_ROWS, Grid=TILE_COLS×VISIBLE_TILE_ROWS）
        """
        return max(0, self.n_chan - per_page)

    # ── 参数计算 ────────────────────────────────────────

    def compute_params(self):
        """从信号前 5 秒数据计算每通道幅值。

        算法: 每通道取 |信号| 的 Y_PERCENTILE 分位作为幅值。
        加载数据后由 app.py 调用一次。
        """
        if self.recon is None:
            return
        sample_len = min(self.n_samples, self.s_freq * 5)
        sample = self.recon[:, :sample_len]
        self.ch_amp = np.maximum(
            np.percentile(np.abs(sample), Y_PERCENTILE, axis=1), 1.0)
        self.window_pts = int(self.window_sec * self.s_freq)

    # ── 参数设置（自动钳制到合理范围）───────────────────

    def set_window(self, sec: float):
        """设置时间窗口。自动钳制到 WINDOW_SEC_MIN ~ WINDOW_SEC_MAX。"""
        self.window_sec = max(WINDOW_SEC_MIN, min(WINDOW_SEC_MAX, sec))
        self.window_pts = int(self.window_sec * self.s_freq)

    def set_amp_scale(self, scale: float):
        """设置幅值缩放。自动钳制到 AMP_SCALE_MIN ~ AMP_SCALE_MAX。"""
        self.amp_scale = max(AMP_SCALE_MIN, min(AMP_SCALE_MAX, scale))

    # ── Y 轴范围计算 ────────────────────────────────────

    def y_range_detail(self, ch: int, y_padding: float = 1.0) -> tuple[float, float]:
        """单个通道 Detail 视图的 Y 轴范围: ±(幅值 × y_padding × 缩放)。

        Args:
            ch:        通道索引
            y_padding: Y 轴上下留白系数（detail.py 传入 DETAIL_Y_PADDING）

        Returns:
            (y_min, y_max)，例如 (-50.0, 50.0)
        """
        if self.ch_amp is None or ch >= len(self.ch_amp):
            return (-100.0, 100.0)
        amp = float(self.ch_amp[ch]) * y_padding * self.amp_scale
        return (-amp, amp)

    def y_offsets_all(self) -> np.ndarray:
        """返回所有 2048 个通道的 Y 偏移数组 (n_chan,)。

        在 grid.build() 时调用一次，之后缓存在 GridView._y_offsets 中。
        仅 2048 × 4 bytes = 8KB，内存可以忽略。
        """
        if self.ch_amp is None:
            return np.zeros(self.n_chan, dtype=np.float32)
        heights = self.ch_amp * SPACING_FACTOR * self.amp_scale
        offsets = np.zeros(self.n_chan, dtype=np.float32)
        cum = 0.0
        # 从最后一个通道（最底部）向上累计
        for i in range(self.n_chan - 1, -1, -1):
            offsets[i] = cum + heights[i] / 2  # 当前通道中心 = 下方累计 + 半高
            cum += heights[i]
        return offsets

