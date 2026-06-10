"""
decimator.py — 数据降采样算法

  将高采样率信号（30k Sa/s × N 秒 = 数万点）压缩到屏幕分辨率级别
  （~1500 点），保留视觉峰值和趋势，丢弃不可见的冗余数据点。

  当前项目不使用运行时降采样。窗口裁剪（grid.py 的 _step_decimate）
  已自然将每曲线点数限制在 ~1500 点。本模块作为备用的精确降采样工具保留。

  参考: Sveinn Steinarsson (2013), "Downsampling Time Series for Visual Representation"

  调参入口: 无。输入输出都是 numpy 数组，不依赖 config.py。
"""

import numpy as np


# ═══════════════════════════════════════════════════════════════
# LTTB — Largest-Triangle-Three-Buckets
#   最常用的时间序列可视化降采样算法
#   原理: 将数据分成 N 个 bucket，每个 bucket 选一个"最能代表趋势"的点
#         选点标准 = 与前后点的三角形面积最大
#   O(n) 时间，O(target) 空间
# ═══════════════════════════════════════════════════════════════

def lttb(data: np.ndarray, target: int) -> np.ndarray:
    """Largest-Triangle-Three-Buckets 降采样。

    将一维信号降至 target 个点，保留视觉峰值和趋势。
    约 0.5ms / 30k 点 / 通道。

    算法步骤:
      1. 保留首尾两个点（确保范围完整）
      2. 将中间的点分成 (target-2) 个 bucket
      3. 每个 bucket 选一个点：该点与上一个选中点、下一个 bucket 平均值
         形成的三角形面积最大 → 最能代表局部趋势

    Args:
        data:   一维 float32 数组
        target: 目标点数（≥ 3，否则直接返回原始数据）

    Returns:
        降采样后的一维数组，长度 target
    """
    n = len(data)
    # 数据太短或目标太少 → 无需降采样，直接返回
    if n <= target or target < 3:
        return data.astype(np.float32, copy=False)

    data = np.asarray(data, dtype=np.float32).ravel()
    out = np.empty(target, dtype=np.float32)

    # 始终保留首尾两点
    out[0] = data[0]
    out[-1] = data[-1]

    # 每个 bucket 的大小（不含首尾）
    bucket_size = (n - 2) / (target - 2)

    # 上一个选中点（初始为首点）
    a_idx = 0
    a_val = data[0]

    for i in range(target - 2):
        # ── 当前 bucket 范围 ──
        bucket_start = int(1 + i * bucket_size)
        bucket_end = int(1 + (i + 1) * bucket_size)
        if bucket_end >= n - 1:
            bucket_end = n - 2
        if bucket_start > bucket_end:
            bucket_start = bucket_end

        # ── 下一个 bucket 的平均值（作为"未来参考点"）──
        next_start = int(1 + (i + 1) * bucket_size)
        next_end = int(1 + (i + 2) * bucket_size)
        if next_end >= n:
            next_end = n - 1
        if next_start > next_end:
            next_start = next_end

        if next_end > next_start:
            next_avg = np.mean(data[next_start:next_end + 1])
        else:
            next_avg = data[next_end]
        next_x = (next_start + next_end) / 2.0

        # ── 在当前 bucket 中找三角形面积最大的点 ──
        max_area = -1.0
        max_idx = bucket_start

        for j in range(bucket_start, bucket_end + 1):
            # 三角形面积公式: |(x_a - x_c)*(y_b - y_a) - (x_a - x_b)*(y_c - y_a)|
            #   a = 上一个选中点, b = 当前候选点, c = 下一个 bucket 平均点
            area = abs((a_idx - next_x) * (data[j] - a_val)
                       - (a_idx - j) * (next_avg - a_val))

            if area > max_area:
                max_area = area
                max_idx = j

        out[i + 1] = data[max_idx]
        a_idx = max_idx
        a_val = data[max_idx]

    return out


# ═══════════════════════════════════════════════════════════════
# MinMax — 极值降采样
#   比 LTTB 更快（每个 bucket 只取 min + max），用于 tile 缩略图
#   保证不会丢失信号的峰值和谷值
# ═══════════════════════════════════════════════════════════════

def minmax(data: np.ndarray, target: int) -> np.ndarray:
    """Min-Max 极值降采样。

    将数据等分为 target 个 bucket，每个 bucket 取最小值和最大值，
    返回 (target × 2,) 数组: [min₁, max₁, min₂, max₂, ...]。

    优势: 速度极快，且绝不会丢失尖峰（spike）。
    劣势: 丢失时间顺序细节。
    适合: Tile 模式缩略图（栅格小，细节不重要）。

    Args:
        data:   一维 float32 数组
        target: bucket 数量

    Returns:
        (target × 2,) float32 数组
    """
    n = len(data)
    data = np.asarray(data, dtype=np.float32).ravel()

    if n <= target * 2:
        return data

    out = np.empty(target * 2, dtype=np.float32)
    bucket_size = n / target

    for i in range(target):
        start = int(i * bucket_size)
        end = int((i + 1) * bucket_size)
        if end <= start:
            end = start + 1
        chunk = data[start:end]
        out[i * 2] = np.min(chunk)       # 谷值
        out[i * 2 + 1] = np.max(chunk)   # 峰值

    return out


# ═══════════════════════════════════════════════════════════════
# 批量通道降采样（目前未使用，保留作为性能优化备选）
# ═══════════════════════════════════════════════════════════════

def decimate_chunk(data_2d: np.ndarray, ch_start: int, ch_count: int,
                   t_start: int, t_end: int, target_pts: int) -> np.ndarray:
    """对一个通道块 + 时间窗口进行批量 LTTB 降采样。

    Args:
        data_2d:    (n_chan, n_samples) 数据数组或 memmap
        ch_start:   起始通道索引
        ch_count:   通道数量
        t_start:    时间轴起始采样点
        t_end:      时间轴结束采样点
        target_pts: LTTB 目标点数

    Returns:
        (ch_count, target_pts) float32 数组

    注意: 此函数目前在热路径中未使用。grid.py 使用 _clip_to_screen()
          做简单的步进降采样，而非每帧调用 LTTB。
    """
    ch_end = min(ch_start + ch_count, data_2d.shape[0])
    actual_count = ch_end - ch_start
    if actual_count <= 0:
        return np.empty((0, target_pts), dtype=np.float32)

    t_slice = slice(t_start, t_end)
    result = np.empty((actual_count, target_pts), dtype=np.float32)

    for i in range(actual_count):
        row = data_2d[ch_start + i, t_slice]
        result[i] = lttb(row, target_pts)

    return result
