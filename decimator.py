"""
decimator.py — 数据降采样

  lttb()            : Largest-Triangle-Three-Buckets — 保留视觉峰值
  minmax()          : Min-Max 降采样 — 更快速，用于缩略图
  decimate_chunk()  : 批量通道降采样

  参考: Sveinn Steinarsson (2013), "Downsampling Time Series for Visual Representation"
"""

import numpy as np


def lttb(data: np.ndarray, target: int) -> np.ndarray:
    """Largest-Triangle-Three-Buckets 降采样。

    将一维信号降至 target 个点，保留视觉峰值和趋势。
    O(n) 时间复杂度。约 0.5ms / 30k 点 / 通道。

    Args:
        data: 一维 float32 数组，长度 n
        target: 目标点数 (>= 2)

    Returns:
        降采样后的一维数组，长度 target
    """
    n = len(data)
    if n <= target or target < 3:
        return data.astype(np.float32, copy=False)

    data = np.asarray(data, dtype=np.float32).ravel()
    out = np.empty(target, dtype=np.float32)

    # 第一个和最后一个点始终保留
    out[0] = data[0]
    out[-1] = data[-1]

    # bucket 大小 (不含首尾)
    bucket_size = (n - 2) / (target - 2)

    # 上一个选中点的索引和值
    a_idx = 0
    a_val = data[0]

    for i in range(target - 2):
        # 当前 bucket 范围
        bucket_start = int(1 + i * bucket_size)
        bucket_end = int(1 + (i + 1) * bucket_size)
        if bucket_end >= n - 1:
            bucket_end = n - 2
        if bucket_start > bucket_end:
            bucket_start = bucket_end

        # 下一个 bucket 的平均值
        next_start = int(1 + (i + 1) * bucket_size)
        next_end = int(1 + (i + 2) * bucket_size)
        if next_end >= n:
            next_end = n - 1
        if next_start > next_end:
            next_start = next_end

        # 下一个 bucket 的平均 x 和平均 y
        if next_end > next_start:
            next_avg = np.mean(data[next_start:next_end + 1])
        else:
            next_avg = data[next_end]
        next_x = (next_start + next_end) / 2.0

        # 在当前 bucket 中选最大三角形面积的点
        max_area = -1.0
        max_idx = bucket_start

        for j in range(bucket_start, bucket_end + 1):
            # 三角形面积 = |(x_a - x_c)*(y_b - y_a) - (x_a - x_b)*(y_c - y_a)| / 2
            area = abs((a_idx - next_x) * (data[j] - a_val)
                       - (a_idx - j) * (next_avg - a_val))

            if area > max_area:
                max_area = area
                max_idx = j

        out[i + 1] = data[max_idx]
        a_idx = max_idx
        a_val = data[max_idx]

    return out


def minmax(data: np.ndarray, target: int) -> np.ndarray:
    """Min-Max 降采样。

    将数据等分为 target 个 bucket，每个 bucket 取 min 和 max，
    返回 (target * 2,) 数组 [min_1, max_1, min_2, max_2, ...]。
    保证信号峰值不会丢失。比 LTTB 更快，适合 tile 缩略图。

    Args:
        data: 一维 float32 数组
        target: bucket 数量

    Returns:
        (target * 2,) float32 数组
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
        out[i * 2] = np.min(chunk)
        out[i * 2 + 1] = np.max(chunk)

    return out


def decimate_chunk(data_2d: np.ndarray, ch_start: int, ch_count: int,
                   t_start: int, t_end: int, target_pts: int) -> np.ndarray:
    """对一个通道块 + 时间窗口进行批量 LTTB 降采样。

    Args:
        data_2d: (n_chan, n_samples) 数据数组或 memmap
        ch_start: 起始通道索引
        ch_count: 通道数量
        t_start: 时间轴起始采样点
        t_end: 时间轴结束采样点
        target_pts: LTTB 目标点数

    Returns:
        (ch_count, target_pts) float32
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
