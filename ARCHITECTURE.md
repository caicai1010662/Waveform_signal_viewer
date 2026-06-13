# 🗺️ SignalViewer 架构速查卡

> 一页纸看懂整个项目的骨架。配合 [LEARN.md](LEARN.md) 渐进学习。

---

## 文件职责一览

```
main.py     → 🚀 启动器：创建 Qt App → 样式表 → MainWindow → 事件循环
config.py   → 🎨 配置中心：颜色、字体、QSS、窗口参数
data.py     → 💾 数据层：.mat加载、.rawcache缓存、SignalData容器、LoaderWorker线程
player.py   → ▶️ 播放引擎：80fps定时器、丢帧保护、循环/单次、变速
grid.py     → 🖼️ 渲染核心：Trace/Grid双模式、对象池、视口剔除、斑马纹
detail.py   → 🔍 详情窗口：单通道放大、µV+Y轴、跟随播放刷新
app.py      → 🧩 主窗口：组装所有UI、滑动条、快捷键、Detail管理
utils.py    → 🔧 工具箱：字体工厂、画笔工厂、通道标签
```

## 依赖图（无循环依赖）

```
config ─────────────────────────────┐
  │                                 │
  ├─→ utils (仅 FONT_FAMILY/SIZE)   │
  │                                 │
  ├─→ data (精灵数据常量)           │
  │     │                           │
  │     └─→ player ◄────────────────┤
  │           │                     │
  │           ├─→ grid ◄────────────┤
  │           │                     │
  │           └─→ detail ◄──────────┤
  │                                 │
  └─→ app ◄────────────────────────┘
        │
        └─→ main
```

## Qt 信号连接总图

```
┌───────────────────────────────────────────────────────────────┐
│                        MainWindow                             │
│                                                               │
│  [Load Data] ──clicked──→ _load_signal()                      │
│  [Trace/Grid]──clicked──→ _on_mode_change()                   │
│  [Start] ──────clicked──→ player.toggle()                     │
│  [Loop/Once] ──clicked──→ player.toggle_loop()                │
│                                                               │
│  Time 滑块 ──valueChanged──→ _on_win_slider()  (标签即时更新) │
│           ──sliderReleased→ _on_win_released() (grid重载)     │
│  Amp  滑块 ──valueChanged──→ _on_amp_slider()                 │
│           ──sliderReleased→ _on_amp_released()                │
│  Speed滑块 ──valueChanged──→ _on_speed_slider()               │
│  Ch   滑块 ──valueChanged──→ _on_ch_scroll()   (30ms防抖)     │
│           ──sliderReleased→ _on_ch_released()                 │
│                                                               │
│  Space ──activated──→ player.toggle()                         │
│  ←/→   ──activated──→ player.seek_delta(±300)                 │
│  ↑/↓   ──activated──→ _ch_up() / _ch_down()                  │
│  Ctrl↑/Ctrl↓ → player.speed_up() / speed_down()               │
│                                                               │
│  ═══════════════ 来自 Player 的信号 ═══════════════           │
│  player.frame_ready ──→ _on_frame() ──→ grid.scroll(ptr)      │
│                      ──→ detail._tick()  (每个detail窗口)     │
│  player.state_changed → _on_state()      (Start↔Pause文字)    │
│  player.loop_changed  → _on_loop_changed() (Loop↔Once文字)    │
│                                                               │
│  ═══════════════ 来自 LoaderWorker 的信号 ═══════════════     │
│  loader.progress ──→ dlg.setLabelText()  (进度对话框)         │
│  loader.finished ──→ on_done()           (数据就绪)           │
│  loader.error_msg ──→ QMessageBox        (错误弹窗)           │
│                                                               │
│  ═══════════════ 来自 GridView 的信号 ═══════════════         │
│  grid.channel_clicked ──→ _open_detail(ch)  (弹出详情窗)      │
└───────────────────────────────────────────────────────────────┘
```

## 渲染热路径（每帧 12.5ms）

```
QTimer(12.5ms)
  │
  ▼
Player._tick()
  ├─ _pending? → 是 → 丢弃本帧（降帧率，不降流畅度）
  └─ 否 → _pending=True
           │
           ▼
         emit frame_ready(ptr) ────────────────────────────┐
           │                                                │
           ▼                                                ▼
    app._on_frame()                               detail._tick()
      │ (每个打开的Detail窗口)
      ├─ ptr+wp > n_samples? → ack() → return               │
      └─ grid.scroll(ptr)                                   │
            │                                               │
            ▼                                               ▼
      _fill_row_data() 或 _fill_tile_data()          curve.setData(t, data[ch, ptr:ptr+wp])
            │
            ├─ recon[abs_ch, t_slice]  ← memmap 零拷贝切片
            ├─ curve.setData(t, 数据+偏移)
            ├─ label.setText() + setPos()
            └─ zebra.setRegion()
            │
            ▼
    player.ack()  ← 释放 _pending 锁，下帧可发射
```

## 内存分布

```
SignalData 实例（常驻内存）
├─ recon: np.memmap    →  0 RAM（硬盘映射，访问时读一小块）
├─ ch_amp: np.ndarray  →  16 KB（2048 × float32）
├─ _y_offsets: np.ndarray → 8 KB（在 GridView 中缓存）
└─ 其他标量            →  忽略不计

GridView 对象池（Trace 模式）
├─ 6 条 PlotDataItem   →  ~几 MB
├─ 6 个 TextItem       →  忽略
├─ 3 条 LinearRegionItem → 忽略
└─ _t_buf: np.ndarray  →  24 KB（window_pts × float32）

总计常驻 RAM < 50 MB（不含 Qt 框架自身）
```

## 关键数字

| 参数 | 值 | 含义 |
|------|-----|------|
| 通道数 | 2048 | 默认数据 |
| 采样率 | 30000 Hz | 每秒 30000 个点 |
| 默认时窗 | 50 ms | 1500 采样点 |
| 帧率 | 80 fps | 每 12.5ms 一帧 |
| 基础播放速度 | 0.005× | 1 数据秒 = 200 真实秒 |
| 对象池大小 | 6 条 | Trace 模式 |
| Tile 栅格 | 6×4=24 | Grid 模式 |
| memmap 内存 | 0 MB | 完全不占 RAM |
