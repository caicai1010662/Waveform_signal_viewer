"""
data.py — 数据加载 + SignalData 容器

  LoaderWorker   : QThread 异步加载 .mat，不阻塞 UI
  load_mat()     : 同步兼容接口
  SignalData     : 数据容器，支持 memmap，所有显示参数由数据驱动

  加载策略:
    - 首次加载 .mat → 提取数据 → 缓存为 .raw (flat float32) → memmap
    - 二次加载 → 直接 memmap .raw 文件（零 RAM 占用）
"""

import os
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import scipy.io as sio
import h5py

from pyqtgraph.Qt import QtCore

from config import WINDOW_SEC, Y_PERCENTILE, WINDOW_SEC_MIN, WINDOW_SEC_MAX, \
    AMP_SCALE_MIN, AMP_SCALE_MAX

warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════════════════════
# Raw 缓存
# ═══════════════════════════════════════════════════════════════

def _raw_cache_path(mat_path: str) -> str:
    """返回 .raw 缓存文件路径。"""
    return mat_path + '.rawcache'


def _has_raw_cache(mat_path: str) -> bool:
    """检查是否已有 .raw 缓存，且比 .mat 更新。"""
    raw = _raw_cache_path(mat_path)
    if not os.path.exists(raw):
        return False
    return os.path.getmtime(raw) >= os.path.getmtime(mat_path)


def _write_raw_cache(mat_path: str, data: np.ndarray):
    """将数据写入 .raw 缓存（flat float32 binary）。"""
    raw_path = _raw_cache_path(mat_path)
    # 写入临时文件然后原子重命名
    tmp = raw_path + '.tmp'
    data.astype(np.float32).tofile(tmp)
    os.replace(tmp, raw_path)


def _open_memmap(mat_path: str, shape: tuple, dtype=np.float32) -> np.ndarray:
    """以 memmap 模式打开 .raw 缓存文件。"""
    raw_path = _raw_cache_path(mat_path)
    return np.memmap(raw_path, dtype=dtype, mode='r', shape=shape)


# ═══════════════════════════════════════════════════════════════
# 采样率检测
# ═══════════════════════════════════════════════════════════════

SFREQ_KEYS = ['s_freq', 'fs', 'Fs', 'sampling_rate',
              'samplerate', 'sample_rate', 'freq']


def _extract_s_freq_from_dict(mat: dict) -> int:
    """从 scipy .mat 字典中查找采样率。"""
    for key in SFREQ_KEYS:
        if key in mat:
            val = np.array(mat[key]).ravel()
            if val.size > 0:
                return int(val[0])
    return 30000


def _extract_s_freq_from_h5(f: h5py.File) -> int:
    """从 h5py File 中查找采样率。"""
    for key in SFREQ_KEYS:
        if key in f:
            val = f[key][()]
            v = np.array(val).ravel()
            if v.size > 0:
                return int(v[0])
    return 30000


# ═══════════════════════════════════════════════════════════════
# 同步加载
# ═══════════════════════════════════════════════════════════════

def _load_mat_sync(path: str, report=None) -> tuple[np.ndarray, int, str]:
    """同步加载 .mat (v5/v7/v7.3)，返回 (data, s_freq, raw_cache_path)。

    尽可能使用 .raw 缓存 + memmap，避免全量加载。
    """
    def _r(msg):
        if report:
            report(msg)

    # ── 尝试 .raw 缓存 ──────────────────────────────────
    if _has_raw_cache(path):
        _r("正在使用缓存...")
        try:
            mat = sio.loadmat(path)
            keys = [k for k in mat if not k.startswith('__')]
            best_key = max(keys, key=lambda k: np.size(mat[k]))
            arr = mat[best_key]
            s_freq = _extract_s_freq_from_dict(mat)
            shape = arr.shape
            del mat, arr
            data = _open_memmap(path, shape)
            return data, s_freq, _raw_cache_path(path)
        except (NotImplementedError, Exception):
            pass

    try:
        # ── v5 / v7 (scipy) ──────────────────────────────
        _r("正在识别文件格式...")
        mat = sio.loadmat(path)
        keys = [k for k in mat if not k.startswith('__')]
        if not keys:
            raise ValueError("未找到有效矩阵变量")

        best_key = max(keys, key=lambda k: np.size(mat[k]))
        _r(f"正在读取数据 ({best_key})...")
        arr = mat[best_key]

        if arr.dtype == np.float32:
            data = arr.copy()
        else:
            data = arr.astype(np.float32, copy=False)

        _r("正在查找采样率...")
        s_freq = _extract_s_freq_from_dict(mat)
        del mat

    except NotImplementedError:
        # ── v7.3 (h5py) ──────────────────────────────────
        _r("正在打开 HDF5 文件...")
        with h5py.File(path, 'r') as f:
            datasets = []

            def _collect(name, obj):
                if isinstance(obj, h5py.Dataset):
                    datasets.append((name, obj))

            f.visititems(_collect)
            valid = [(n, o) for n, o in datasets if '#' not in n]
            if not valid:
                raise ValueError("未找到有效矩阵变量")

            best_name, best_ds = max(valid, key=lambda x: x[1].size)
            _r(f"正在读取数据 ({best_name})...")
            data = np.array(best_ds, dtype=np.float32)

            _r("正在查找采样率...")
            s_freq = _extract_s_freq_from_h5(f)

    _r("正在校验数据...")
    if data.ndim != 2:
        raise ValueError(f"数据维度异常: {data.ndim}D (需要 2D)")

    # ── 写入 .raw 缓存 ──────────────────────────────────
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
# LoaderWorker — 异步加载
# ═══════════════════════════════════════════════════════════════

class LoaderWorker(QtCore.QThread):
    """异步加载 .mat 文件，不阻塞 UI。"""

    progress = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(np.ndarray, int, str)   # (data, s_freq, cache_path)
    error_msg = QtCore.pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            data, s_freq, raw_path = _load_mat_sync(self.path, self._report)
            self.progress.emit("加载完成")
            self.finished.emit(data, s_freq, raw_path)
        except Exception as e:
            self.error_msg.emit(str(e))

    def _report(self, msg: str):
        self.progress.emit(msg)


# ═══════════════════════════════════════════════════════════════
# 同步兼容接口
# ═══════════════════════════════════════════════════════════════

def load_mat(path: str) -> np.ndarray:
    """同步加载 .mat（兼容旧接口），仅返回 data。"""
    data, _, _ = _load_mat_sync(path)
    return data


# ═══════════════════════════════════════════════════════════════
# SignalData
# ═══════════════════════════════════════════════════════════════

@dataclass
class SignalData:
    """持有原始和重建数据，所有显示参数由数据统计特性决定。

    支持 memmap：首次加载后数据以 .raw 缓存 + memmap 形式存储，
    后续加载零 RAM 占用。
    """

    orig: Optional[np.ndarray] = None
    recon: Optional[np.ndarray] = None
    orig_path: str = ""
    recon_path: str = ""
    s_freq: int = 30000
    n_chan: int = 0
    n_samples: int = 0
    window_pts: int = 0

    # 用户可调
    window_sec: float = WINDOW_SEC
    amp_scale: float = 1.0

    # 由数据计算
    ch_amp: Optional[np.ndarray] = None   # (n_chan,) 每通道幅值 (µV)
    ch_amp_computed: bool = False

    @property
    def ready(self) -> bool:
        return self.orig is not None and self.recon is not None

    @property
    def total_rows(self) -> int:
        """总行数（每行一个通道）。"""
        if self.n_chan == 0:
            return 0
        return self.n_chan

    @property
    def max_channel_offset(self) -> int:
        """通道浏览滑块最大值。"""
        return max(0, self.n_chan - 1)

    # ── 参数计算 ──────────────────────────────────────────

    def compute_params(self):
        """从原始信号前 5 秒计算每通道幅值（percentile）。"""
        if self.orig is None:
            return
        sample_len = min(self.n_samples, self.s_freq * 5)
        sample = self.orig[:, :sample_len]
        self.ch_amp = np.maximum(
            np.percentile(np.abs(sample), Y_PERCENTILE, axis=1), 1.0)
        self.window_pts = int(self.window_sec * self.s_freq)
        self.ch_amp_computed = True

    # ── 参数设置 ──────────────────────────────────────────

    def set_window(self, sec: float):
        self.window_sec = max(WINDOW_SEC_MIN, min(WINDOW_SEC_MAX, sec))
        self.window_pts = int(self.window_sec * self.s_freq)

    def set_amp_scale(self, scale: float):
        self.amp_scale = max(AMP_SCALE_MIN, min(AMP_SCALE_MAX, scale))

    # ── Y 范围 ────────────────────────────────────────────

    def y_range_detail(self, ch: int) -> tuple[float, float]:
        """单个通道的 Y 轴范围：±(幅值 × 1.2 × 缩放倍率)。"""
        if self.ch_amp is None or ch >= len(self.ch_amp):
            return (-100.0, 100.0)
        amp = float(self.ch_amp[ch]) * 1.2 * self.amp_scale
        return (-amp, amp)

    def y_offset(self, ch: int) -> float:
        """返回通道 ch 的 Y 堆叠偏移量（Row 模式）。"""
        if self.ch_amp is None:
            return float(ch) * 100.0
        from config import SPACING_FACTOR
        heights = self.ch_amp * SPACING_FACTOR * self.amp_scale
        cum = 0.0
        for i in range(self.n_chan - 1, ch, -1):
            cum += heights[i]
        return cum + heights[ch] / 2

    def y_offsets_all(self) -> np.ndarray:
        """返回所有通道的 Y 堆叠偏移。"""
        if self.ch_amp is None:
            return np.zeros(self.n_chan, dtype=np.float32)
        from config import SPACING_FACTOR
        heights = self.ch_amp * SPACING_FACTOR * self.amp_scale
        offsets = np.zeros(self.n_chan, dtype=np.float32)
        cum = 0.0
        for i in range(self.n_chan - 1, -1, -1):
            offsets[i] = cum + heights[i] / 2
            cum += heights[i]
        return offsets

    @property
    def total_y_height(self) -> float:
        if self.ch_amp is None:
            return self.n_chan * 100.0
        from config import SPACING_FACTOR
        return float(np.sum(self.ch_amp * SPACING_FACTOR * self.amp_scale))
