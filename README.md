# SignalViewer — 2048 通道神经信号对比查看器

Rawdata vs Recdata 并排对比。VS Code Dark Theme 像素级复刻。2048 通道 @ 30k Sa/s，80fps 流畅播放。

## 快速开始

```bash
pack_env\Scripts\activate
python main.py
```

## 操作方式

### 键盘快捷键

| 键位 | 功能 |
|------|------|
| `Space` | 播放 / 暂停 |
| `←` | 时间轴步退 10ms（300 采样点） |
| `→` | 时间轴步进 10ms |
| `↑` | 通道向上滚动 1 行 |
| `↓` | 通道向下滚动 1 行 |
| `Ctrl+↑` | 播放速度加快一档 |
| `Ctrl+↓` | 播放速度减慢一档 |

### 鼠标

| 操作 | 功能 |
|------|------|
| 点击通道波形 | 弹出该通道的 Detail 详情窗口 |

## 三种显示模式

| 模式 | 触发 | 说明 |
|------|------|------|
| **Compare** | Compare 按钮 | 一行一个通道，左侧 Rawdata + 右侧 Recdata。奇偶行斑马纹交替底色。 |
| **Browse** | Browse 按钮 | TILE_COLS 列 × VISIBLE_TILE_ROWS 行栅格。每个 tile 带边框区分相邻通道。 |
| **Detail** | 点击通道弹出 | 独立窗口，单通道放大。Overlay 叠加 / Side-by-Side 并排可切换。跟随播放实时刷新。 |

## 顶栏布局

```
[Load Rawdata] [Load Recdata] | [Compare] [Browse] | [Start] [Loop]   Time: [50ms] ━━   Amp: [1.0×] ━━   Speed: [1.0×] ━━   00:00.000
```

- **Load Rawdata**: 加载原始信号 .mat → 启用 Load Recdata 按钮
- **Load Recdata**: 加载重建信号 .mat → 通道数校验（支持自动转置）→ 长度对齐 → 构建视图
- **Compare / Browse**: 互斥 Toggle 按钮，切换显示模式
- **Start / Pause**: 播放控制，文字随状态切换
- **Loop / Once**: 循环模式开关，默认循环
- **Time**: 时间窗口 50ms~100ms（`WINDOW_SEC_MIN` ~ `MAX`）
- **Amp**: 幅值缩放 1.0×~3.0×（`AMP_SCALE_MIN` ~ `MAX`）
- **Speed**: 播放速度 0.5×~1.5×（`SPEED_MUL_MIN` ~ `MAX`）
- **右侧垂直滑块**: 通道浏览，上下拖动切换可见通道范围
- **最右侧时间戳**: 当前窗口在整段记录中的绝对时间（`MM:SS.sss`）

### 滑动条交互模型

三种策略按场景区分：

| 滑动条 | 拖动时 | 松手时 | 原因 |
|--------|--------|--------|------|
| Time / Amp | 标签数值即时更新 | 一次性 grid 重载 | 只需看结果，无需中间重绘 |
| Speed | 即时更新 | — | `player.set_speed()` 无重绘开销 |
| **Channel** | 30ms 短防抖（~33fps 视觉反馈） | 立即定格 | 需要看到通道变化来定位 |

## 项目结构（9 个 .py 文件）

```
SignalViewer/
├── main.py              程序入口 — QApplication + 样式表 + MainWindow
├── config.py             ⭐ 全局调参中心 — 颜色、字号、间距、QSS、窗口启动参数
├── data.py               .mat 加载 + .rawcache memmap 缓存 + LoaderWorker 异步线程
├── player.py             播放引擎 — 80fps 精确帧率，_pending 锁丢帧保护
├── grid.py               核心渲染（~700 行）— Compare/Browse 双模式，对象池 + 视口剔除
├── detail.py             单通道 Detail 窗口 — Overlay/Side-by-side
├── decimator.py          LTTB + MinMax 降采样算法（备用）
├── app.py                主窗口 — 控件 + 滑动条 + 键盘绑定 + Detail 管理
├── utils.py              字体工厂（make_font）+ 画笔工厂（make_pen）+ 通道标签格式化
├── logo.ico              应用图标
├── SignalViewer.spec     PyInstaller 打包配置
├── .gitignore
├── sample_data/          测试数据
└── pack_env/             Python 虚拟环境
```

### 依赖链（无循环依赖）

```
config → data → player → grid/detail → app → main
```

## 配色方案（VS Code Dark Theme）

| 变量 | 色值 | 用途 |
|------|------|------|
| `COLOR_BG` | `#181818` | 窗口最外层底色 |
| `COLOR_CARD` | `#1E1E1E` | 波形面板底色 |
| `COLOR_ORIG` | `#4FC1FF` | 原始信号曲线（亮蓝） |
| `COLOR_RECON` | `#DCDCAA` | 重建信号曲线（暖黄） |
| `COLOR_TEXT` | `#FFFFFF` | 所有文字 |
| `COLOR_SEP` | `#474748` | 中轴分隔线 / Tile 边框 |
| `COLOR_ACCENT` | `#007ACC` | 按钮选中、滑块手柄 |
| `COLOR_ZEBRA` | `#2A2A2A` | 斑马纹交替行底色 |
| `COLOR_SLIDER` | `#464646` | 滑动条轨道 |
| `COLOR_GRID` | `#4A4A4A` | Detail 窗坐标轴线 |
| `COLOR_HOVER` | `#2A2D2E` | 鼠标悬停 |

## 字体

| 参数 | 值 |
|------|-----|
| `FONT_FAMILY` | `"Microsoft YaHei Mono"`（等宽中英文，QSS 回退 Consolas） |
| `FONT_SIZE` | 16px 全局统一 |
| 加粗 | QSS `font-weight: bold` + `QFont.setBold(True)` 双重保证 |

**注意**: pyqtgraph 的 `TextItem` / `AxisItem.label` 不走 QSS，必须用 `make_font()` 单独设字体。
`make_font()` 内部使用 `setBold(True)` 而非 `setWeight()`——PyQt5 的 `setWeight` 仅接受 0~99 枚举值，不接受 CSS 的 400/700 权重。

## 配置参数速查

### 启动参数（config.py §〇）

```python
WIN_WIDTH  = 1920      # 窗口初始宽度（像素）
WIN_HEIGHT = 1080      # 窗口初始高度
WIN_X = -1             # -1=自动居中， 0=贴左边， 960=右半边
WIN_Y = -1             # -1=自动居中， 0=贴顶端
WIN_MAXIMIZED = False  # True=启动全屏
WIN_TITLE = "SignalViewer"
DETAIL_OFFSET_X = 30   # Detail 窗相对主窗 X/Y 偏移
DETAIL_OFFSET_Y = 30
```

### 显示与布局

```python
WINDOW_SEC = 0.05       # 默认时间窗口 50ms
TARGET_FPS = 80         # 目标帧率
PLAYBACK_SPEED = 0.005  # 基础播放速度（数据秒/真实秒）
LINE_WIDTH = 1.2        # 波形线宽

TILE_COLS = 6           # Browse 每行格子数
VISIBLE_ROWS = 6        # Compare 一屏可见行数
VISIBLE_TILE_ROWS = 4   # Browse 一屏可见行数
```

### 滑动条范围

```python
WINDOW_SEC_MIN = 0.05   # 时窗下限
WINDOW_SEC_MAX = 0.10   # 时窗上限
AMP_SCALE_MIN  = 1.0    # 幅值下限
AMP_SCALE_MAX  = 3.0    # 幅值上限
SPEED_MUL_MIN  = 0.5    # 速度下限
SPEED_MUL_MAX  = 1.5    # 速度上限
```

### 数据驱动

```python
Y_PERCENTILE = 99.9     # 通道幅值估算百分位
SPACING_FACTOR = 3      # 通道间距系数
```

## 关键设计决策

### 视觉

- **无零基线**: 所有模式不显示 Y=0 虚线参考线，画面保持干净
- **斑马纹**: Compare 模式偶数行 `COLOR_ZEBRA` 底色（`LinearRegionItem`），奇数行 `COLOR_CARD`，左右同步
- **Tile 边框**: Browse 模式每个 tile 的 ViewBox 加 `COLOR_SEP` 1px 边框，在密集栅格中区分相邻通道
- **通道标签左下角**: `anchor=(0,1)` + `setZValue(100)`，绝对置顶不被波形遮挡
- **标签动态背景**: Compare 模式标签底色跟随斑马纹（偶数=ZEBRA，奇数=CARD）
- **X 轴 2% 呼吸空间**: 左右各 `window_sec × 0.02` padding，波形不贴边

### 性能

- **对象池**: 只创建 VISIBLE_ROWS 条曲线，通过 `setData()` 换绑数据，从不创建新对象
- **memmap 零 RAM**: `.rawcache` 缓存 + `np.memmap` 映射，后续加载同一文件零 RAM 占用
- **缓存校验**: `.rawcache` 命中后校验文件大小（`os.path.getsize`），同名覆盖导致内容变化时自动删除脏缓存并重载
- **视口剔除**: 只渲染当前可见通道，其余不参与渲染管线
- **步进降采样**: `_step_decimate` — 每曲线超过 6000 点才触发。正常 window_pts≈1500，实际不做裁剪
- **_t_buf 复用**: 只在 window_pts 变化时重新分配 `np.arange`，避免每帧分配数组的 GC 压力
- **无 OpenGL / 无抗锯齿**: `pg.setConfigOptions(antialias=False, useOpenGL=False)`
- **异步加载**: `LoaderWorker(QThread)` 后台线程 + `QProgressDialog`，UI 永不卡顿
- **加载锁**: `_load_mat_async` 检查 `isRunning()`，防止双击按钮引发并发加载

### 渲染管线（每帧热路径）

```
Player._tick() → frame_ready(ptr) → app._on_frame() → grid.scroll(ptr)
  → _fill_row_data() 或 _fill_tile_data()
    → memmap[ch, ptr:ptr+wp] 切片（零拷贝）
    → curve.setData() 换绑
    → 更新 label 位置 + 斑马纹区域
  → player.ack() 释放 _pending 锁
```

`_on_frame` 中所有出口（正常/越界/异常）都调 `ack()`，`_pending` 锁永不卡死。

## Detail 窗口

- **触发**: 点击 Compare 或 Browse 中的任意通道
- **Overlay 模式**（默认）: 两条曲线叠加在同一 PlotItem，图例区分 Rawdata/Recdata
- **Side-by-Side 模式**: 左右两个独立 PlotItem 并排
- **生命周期**: `WeakSet` 管理，同一通道不重复创建，关闭自动 `disconnect` 信号
- **仅更新可见面板**: 隐藏模式的曲线不调 `setData()`

## 数据加载流程

```
用户点击 "Load Rawdata (.mat)" → QFileDialog → LoaderWorker(path).start()
  → 后台线程: _load_mat_sync()
    1. 检查 .rawcache 缓存 → 有则校验文件大小 → memmap（秒开）
    2. 大小不匹配 → 删除脏缓存 → 回退全量加载
    3. 无缓存 → scipy.loadmat（v5/v7）或 h5py（v7.3）
    4. 查找采样率（SFREQ_KEYS 遍历）→ float32 → 写入 .rawcache → memmap
  → 主线程: finished 信号 → 填充 sd.orig → 启用 Load Recdata 按钮

用户点击 "Load Recdata (.mat)" → 同上流程
  → 通道数校验（支持自动转置修正）
  → 长度对齐（取较短者截断）
  → compute_params() — 前 5 秒数据 × 99.9 分位 → ch_amp
  → grid.build() — 对象池 + 斑马纹 + 标签 + Tile 边框
  → 启用所有控件（播放按钮 + 4 个滑动条）
```

## 打包

```bash
pyinstaller SignalViewer.spec
# 输出: dist/SignalViewer.exe（无命令行窗口，带图标）
```

## 已知边界

- **PyQt5**: `QFont.setWeight()` 不接受 CSS 权重值（如 700），必须用 `setBold(True)` 布尔值
- **pyqtgraph**: `TextItem` 和 `AxisItem.label` 不响应 QSS 样式表，必须代码设 `QFont`
- **memmap**: `.rawcache` 须保持与 .mat 同级目录且不被外部修改，已加文件大小校验兜底
- **键盘**: `_bind_keys` 中所有快捷键绑定到 `MainWindow`，Detail 窗获得焦点时部分快捷键不生效（Qt 的 `QShortcut` 作用域限制）
