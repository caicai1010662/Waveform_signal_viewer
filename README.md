# SignalViewer — 多通道神经信号查看器

单信号高速渲染。VS Code Dark Theme。多通道 @ 30k Sa/s，80fps 流畅播放。

> 🎓 **小白入门？** 先读 [LEARN.md](LEARN.md) — 从零开始的渐进式学习指南，附带实验和检查清单。

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
| **Trace** | Trace 按钮 | 一行一个通道，垂直堆叠。奇偶行斑马纹交替底色。 |
| **Grid** | Grid 按钮 | TILE_COLS 列 × VISIBLE_TILE_ROWS 行栅格。每个 tile 带边框区分相邻通道。 |
| **Detail** | 点击通道弹出 | 独立窗口，单通道放大。跟随播放实时刷新。 |

## 顶栏布局

```
[Load Data] | [Trace] [Grid] | [Start] [Loop]   Time: [50ms] ━━   Amp: [1.0×] ━━   Speed: [1.0×] ━━   00m 00.000s
```

- **Load Data**: 加载 .mat 信号文件 → 计算通道幅值 → 构建视图 → 启用所有控件
- **Trace / Grid**: 互斥 Toggle 按钮，切换显示模式
- **Start / Pause**: 播放控制，文字随状态切换
- **Loop / Once**: 循环模式开关，默认循环
- **Time**: 时间窗口（`WINDOW_SEC_MIN` ~ `WINDOW_SEC_MAX`，data.py 顶部）
- **Amp**: 幅值缩放（`AMP_SCALE_MIN` ~ `AMP_SCALE_MAX`，data.py 顶部）
- **Speed**: 播放速度（`SPEED_MUL_MIN` ~ `SPEED_MUL_MAX`，player.py 顶部）
- **右侧垂直滑块**: 通道浏览，上下拖动切换可见通道范围
- **最右侧时间戳**: 当前绝对时间，格式 `00m 00.000s`

### 滑动条交互模型

| 滑动条 | 拖动时 | 松手时 | 原因 |
|--------|--------|--------|------|
| Time / Amp | 标签数值即时更新 | 一次性 grid 重载 | 只需看结果，无需中间重绘 |
| Speed | 即时更新 | — | `player.set_speed()` 无重绘开销 |
| **Channel** | 30ms 短防抖（~33fps 视觉反馈） | 立即定格 | 需要看到通道变化来定位 |

## 文档

| 文档 | 适合 |
|------|------|
| [LEARN.md](LEARN.md) | 🎓 小白渐进式学习，从零吃透项目 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 🗺️ 架构速查卡，信号连接、渲染管线、内存分布 |

## 项目结构（8 个 .py 文件）

```
SignalViewer/
├── main.py              程序入口 — QApplication + 样式表 + MainWindow
├── config.py             全局配置 — 颜色、字体、QSS、窗口启动参数
├── data.py               .mat 加载 + .rawcache memmap 缓存 + LoaderWorker 异步线程
├── player.py             播放引擎 — 80fps 精确帧率，_pending 锁丢帧保护
├── grid.py               核心渲染 — Trace/Grid 双模式，对象池 + 视口剔除
├── detail.py             单通道 Detail 窗口
├── app.py                主窗口 — 控件 + 滑动条 + 键盘绑定 + Detail 管理
├── utils.py              字体（make_font）+ 画笔（make_pen）+ 通道标签
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

### 参数分布

参数不再堆在 config.py，而是放在各自模块顶部：

| 模块 | 参数 |
|------|------|
| **data.py** | WINDOW_SEC, WINDOW_SEC_MIN/MAX, AMP_SCALE_MIN/MAX, Y_PERCENTILE, SPACING_FACTOR |
| **player.py** | TARGET_FPS, PLAYBACK_SPEED, SPEED_MUL_MIN/MAX |
| **grid.py** | TILE_COLS, VISIBLE_ROWS, VISIBLE_TILE_ROWS, LINE_WIDTH |
| **detail.py** | DETAIL_FONT_*, DETAIL_Y_PADDING, DETAIL_X_PADDING, DETAIL_OFFSET_* |

## 配色方案（VS Code Dark Theme）

| 变量 | 色值 | 用途 |
|------|------|------|
| `COLOR_BG` | `#181818` | 窗口最外层底色 |
| `COLOR_CARD` | `#1E1E1E` | 波形面板底色 |
| `COLOR_SIGNAL` | `#DCDCAA` | 信号曲线（暖黄） |
| `COLOR_TEXT` | `#FFFFFF` | 所有文字 |
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

**注意**: pyqtgraph 的 `TextItem` / `AxisItem.label` 不走 QSS，必须用 `make_font()` 单独设字体。`LabelItem`（图例、轴标题）用 HTML 渲染，字体需通过 `family`/`size`/`bold` 参数传入。

## 配置参数速查

### 启动参数（config.py）

```python
WIN_WIDTH  = 1920      # 窗口初始宽度（像素）
WIN_HEIGHT = 1080      # 窗口初始高度
WIN_X = -1             # -1=自动居中
WIN_Y = -1
WIN_MAXIMIZED = False  # True=启动全屏
WIN_TITLE = "SignalViewer"
```

### 显示与布局（data.py / grid.py）

```python
WINDOW_SEC = 0.05       # 默认时间窗口 50ms
TILE_COLS = 6            # Grid 每行格子数
VISIBLE_ROWS = 6         # Trace 一屏可见行数
VISIBLE_TILE_ROWS = 4    # Grid 一屏可见行数
LINE_WIDTH = 1.2         # 波形线宽
```

### 滑动条范围（data.py / player.py）

```python
WINDOW_SEC_MIN = 0.05   # 时窗下限
WINDOW_SEC_MAX = 0.10   # 时窗上限
AMP_SCALE_MIN  = 1.0    # 幅值下限
AMP_SCALE_MAX  = 3.0    # 幅值上限
SPEED_MUL_MIN  = 0.5    # 速度下限
SPEED_MUL_MAX  = 1.5    # 速度上限
```

### 数据驱动（data.py）

```python
Y_PERCENTILE = 99.9     # 通道幅值估算百分位
SPACING_FACTOR = 3      # 通道间距系数
```

## Detail 窗口（detail.py 顶部调参）

- **触发**: 点击 Trace 或 Grid 中的任意通道
- **单曲线放大**: 独立窗口，跟播实时刷新
- **坐标轴**: µV（左）+ Time (s)（底），实线外框 + 虚网格线
- **生命周期**: `WeakSet` 管理，同一通道不重复创建，关闭自动断开信号
- **参数**: `DETAIL_FONT_TICK=15`、`DETAIL_FONT_LABEL=50`、`DETAIL_GRID_ALPHA=0.9`、`DETAIL_Y_PADDING=1.0`、`DETAIL_X_PADDING=0.02`

## 关键设计决策

### 视觉

- **无零基线**: 所有模式不显示 Y=0 参考线，画面干净
- **斑马纹**: Trace 模式偶数行 `COLOR_ZEBRA` 底色（`LinearRegionItem`），奇数行 `COLOR_CARD`
- **Tile 边框**: Grid 模式每个 tile 的 ViewBox 加 1px 边框，密集栅格中区分相邻通道
- **通道标签左下角**: `anchor=(0,1)` + `setZValue(100)`，置顶不被波形遮挡
- **标签动态背景**: Trace 模式标签底色跟随斑马纹（偶数=ZEBRA，奇数=CARD）
- **X 轴呼吸空间**: Row 模式左右各 2% padding，Detail 窗通过 `DETAIL_X_PADDING` 控制

### 性能

- **对象池**: 只创建 VISIBLE_ROWS 条曲线，`setData()` 换绑，从不新建对象
- **memmap 零 RAM**: `.rawcache` + `np.memmap`，加载后零 RAM 占用
- **缓存校验**: `.rawcache` 命中后校验文件大小，同名覆盖自动删除脏缓存并重载
- **视口剔除**: 只渲染当前可见通道
- **步进降采样**: `_step_decimate` — 超 6000 点才触发，正常 window_pts≈1500 不做裁剪
- **_t_buf 复用**: 只在 window_pts 变化时重新分配 `np.arange`
- **无 OpenGL / 无抗锯齿**: `pg.setConfigOptions(antialias=False, useOpenGL=False)`
- **异步加载**: `LoaderWorker(QThread)` + `QProgressDialog`，UI 不卡顿
- **加载锁**: `_load_mat_async` 检查 `isRunning()`，防双击并发

### 渲染管线（每帧热路径）

```
Player._tick() → frame_ready(ptr) → app._on_frame() → grid.scroll(ptr)
  → _fill_row_data() 或 _fill_tile_data()
    → memmap[ch, ptr:ptr+wp] 切片（零拷贝）
    → curve.setData() 换绑
    → 更新 label 位置 + 斑马纹区域
  → player.ack() 释放 _pending 锁
```

## 数据加载流程

```
点击 "Load Data (.mat)" → QFileDialog → LoaderWorker(path).start()
  → 后台线程: _load_mat_sync()
    1. 检查 .rawcache 缓存 → 有则校验文件大小 → memmap（秒开）
    2. 大小不匹配 → 删除脏缓存 → 回退全量加载
    3. 无缓存 → scipy.loadmat（v5/v7）或 h5py（v7.3）
    4. 查找采样率 → float32 → 写入 .rawcache → memmap
  → 主线程: finished 信号 → 填充 sd.recon
  → compute_params() — 前 5 秒 × 99.9 分位 → ch_amp
  → grid.build() — 对象池 + 斑马纹 + 标签 + Tile 边框
  → 启用所有控件
```

## 打包

```bash
pyinstaller SignalViewer.spec
# 输出: dist/SignalViewer.exe（无命令行窗口，带图标）
```

## 已知边界

- **PyQt5**: `QFont.setWeight()` 不接受 CSS 权重，必须用 `setBold(True)`
- **pyqtgraph**: `TextItem` 和 `LabelItem` 不响应 QSS，必须代码设字体
- **LabelItem**: 图例和轴标题用 HTML 渲染，`setFont()` 无效，需 `setText(text, size=, family=, bold=)`
- **memmap**: `.rawcache` 须与 .mat 同级目录且不被外部修改
- **键盘**: Detail 窗获得焦点时部分快捷键不生效（Qt `QShortcut` 作用域限制）
