# SignalViewer — 2048 通道神经信号对比查看器

Rawdata vs Recdata 并排对比。VS Code Dark Theme 像素级复刻。2048 通道 @ 30k Sa/s，80fps 流畅播放。

## 快速开始

```bash
pack_env\Scripts\activate
python main.py
```

## 操作方式

**只有两个控制：Space 键 + 鼠标点击。**

| 操作 | 功能 |
|------|------|
| `Space` | 播放 / 暂停（唯一键盘快捷键） |
| 鼠标点击通道波形 | 弹出该通道的 Detail 窗口 |

## 三种显示模式

| 模式 | 按钮 | 说明 |
|------|------|------|
| **Compare** | Compare 按钮 | 一行一个通道，左侧 Rawdata + 右侧 Recdata。每屏 VISIBLE_ROWS（6）行，通道间斑马纹交替底色。 |
| **Browse** | Browse 按钮 | TILE_COLS（6）列 × VISIBLE_TILE_ROWS（4）行 = 24 通道栅格。左侧 Rawdata 栅格 + 右侧 Recdata 栅格。 |
| **Detail** | 点击通道弹出 | 独立窗口，单通道放大。Overlay 叠加 / Side-by-Side 并排两种子模式可切换。跟随播放实时刷新。 |

## 项目结构（9 个 .py 文件）

```
SignalViewer/
├── main.py              程序入口 — 创建 QApplication + 加载样式表 + 显示 MainWindow
├── config.py             ⭐ 全局调参中心 — 所有颜色、字号、间距、滑动条范围、QSS 样式表
├── data.py               .mat 加载（scipy/h5py）+ .rawcache memmap 缓存 + LoaderWorker 异步线程
├── player.py             播放引擎 — QTimer 精确驱动，80fps，Loop/Once，0.5×~1.5× 变速
├── grid.py               核心渲染模块（~700 行）— Compare + Browse 双模式，对象池 + 视口剔除
├── detail.py             单通道 Detail 弹出窗口 — Overlay/Side-by-side 切换
├── decimator.py          LTTB + MinMax 降采样算法（备用，当前热路径使用 grid._step_decimate）
├── app.py                主窗口 — 顶栏控件 + 滑动条 + 文件加载 + Detail 窗口管理
├── utils.py              字体工厂（make_font）+ 画笔工厂（make_pen）+ 通道标签格式化
├── logo.ico              应用图标
├── SignalViewer.spec     PyInstaller 打包配置
├── .gitignore
└── pack_env/             Python 虚拟环境
```

### 依赖链（无循环依赖）

```
config → data → player → grid/detail → app → main
```

## 顶栏布局

```
[Load Rawdata] [Load Recdata] | [Compare] [Browse] | [Start] [Loop]   Time: [50ms] ━━   Amp: [1.0×] ━━   Speed: [1.0×] ━━
```

- **Load Rawdata**: 加载原始信号 .mat → 启用 Load Recdata 按钮
- **Load Recdata**: 加载重建信号 .mat → 通道校验 → 自动截断对齐 → 构建视图 → 启用所有控件
- **Compare / Browse**: 互斥 Toggle 按钮（QButtonGroup），切换显示模式
- **Start / Pause**: 播放控制，文字随状态切换
- **Loop / Once**: 循环模式 Toggle，默认 Loop
- **Time 滑动条**: 0-1000 映射到 WINDOW_SEC_MIN~MAX（50ms~100ms）
- **Amp 滑动条**: 0-1000 映射到 AMP_SCALE_MIN~MAX（1.0×~3.0×）
- **Speed 滑动条**: 0-1000 映射到 SPEED_MUL_MIN~MAX（0.5×~1.5×）
- **右侧垂直滑动条**: 通道浏览，上下拖动切换可见通道范围

## 配色方案（VS Code Dark Theme）

| 变量 | 色值 | 用途 |
|------|------|------|
| `COLOR_BG` | `#181818` | 窗口最外层底色 |
| `COLOR_CARD` | `#1E1E1E` | 波形面板底色（与 BG 形成层级感） |
| `COLOR_ORIG` | `#4FC1FF` | 原始信号波形颜色（亮蓝） |
| `COLOR_RECON` | `#DCDCAA` | 重建信号波形颜色（暖黄） |
| `COLOR_TEXT` | `#FFFFFF` | 所有文字颜色 |
| `COLOR_SEP` | `#3E3E42` | 左右面板中轴分隔线 |
| `COLOR_ACCENT` | `#007ACC` | 交互强调色（按钮选中、滑块手柄） |
| `COLOR_ZEBRA` | `#222222` | 斑马纹交替行底色 |
| `COLOR_SLIDER` | `#464646` | 滑动条轨道底色 |
| `COLOR_GRID` | `#4A4A4A` | Detail 窗坐标轴线颜色 |
| `COLOR_HOVER` | `#2A2D2E` | 鼠标悬停底色 |

## 字体

| 参数 | 值 |
|------|-----|
| `FONT_FAMILY` | `"Microsoft YaHei Mono"`（等宽中英文，QSS 回退到 Consolas） |
| `FONT_SIZE` | 16px 全局统一 |
| 加粗 | 全局 `font-weight: bold` — QSS 样式表 + `QFont.setBold(True)` 程序双重保证 |

**重要**: pyqtgraph 的 `TextItem` / `AxisItem.label` 不走 QSS 样式表，必须通过 `setFont(make_font(...))` 单独设置。`make_font()` 使用 `setBold(True)` 而非 `setWeight()`（PyQt5 的 `setWeight` 仅接受 0-99 枚举，不接受 CSS weight 值）。

## 关键设计决策

### 视觉
- **无零基线**: 所有模式均不显示 Y=0 处的虚线参考线，波形画面保持干净
- **斑马纹贯穿左右**: Compare 模式下偶数行左右两侧同步绘制 `COLOR_ZEBRA` 底色（`LinearRegionItem`），奇数行保留 `COLOR_CARD` 底色
- **通道标签左下角**: `anchor=(0,1)` + `setZValue(100)` 确保标签绝对置顶、不被波形遮挡
- **标签动态背景**: 偶数行标签背景 = `COLOR_ZEBRA`，奇数行 = `COLOR_CARD`，与斑马纹融为一体
- **X 轴 2% 呼吸空间**: 左右各留 `window_sec × 0.02` padding，防止波形贴边
- **Tile 栅格 2px 间距**: `GraphicsLayoutWidget.ci.layout.setSpacing(2)` — 深色底（`COLOR_BG`）透过间距形成自然网格线

### 性能
- **对象池**: 只创建 VISIBLE_ROWS（6）条曲线，滚动时通过 `setData()` 换绑数据，从不创建新对象
- **memmap 零 RAM**: 首次加载 .mat → 写入 .rawcache 文件 → `np.memmap` 映射。后续加载同一文件零 RAM 占用
- **视口剔除**: 只渲染当前可见通道，其他 2042 个通道不参与渲染
- **步进降采样**: `_step_decimate()` — 每曲线数据点超过 MAX_POINTS_PER_CURVE（6000）时自动步进取样。正常 window_pts ≈ 1500，远低于上限，实际不做任何裁剪
- **时间轴复用**: `_t_buf` 只在 window_pts 变化时重新分配，避免每帧 `np.arange(1500)`
- **无 OpenGL**: `pg.setConfigOptions(useOpenGL=False)` — 集成显卡下 OpenGL 反而更慢
- **无抗锯齿**: `pg.setConfigOptions(antialias=False)` — 神经信号不需要平滑边缘
- **异步加载**: `LoaderWorker(QThread)` 后台加载 .mat，主线程显示 QProgressDialog，UI 永不卡顿

### 渲染管线（每帧热路径）

```
Player._tick() → frame_ready(ptr) → app._on_frame() → grid.scroll(ptr)
  → _fill_row_data() 或 _fill_tile_data()
    → memmap[ch, ptr:ptr+wp] 切片（零拷贝）
    → curve.setData() 换绑
    → 更新 label 位置 + zebra 区域
  → player.ack() 释放 _pending 锁
```

## 配置参数速查

```python
# 显示
WINDOW_SEC = 0.05       # 默认时间窗口 50ms
TARGET_FPS = 80         # 目标帧率
PLAYBACK_SPEED = 0.005   # 基础播放速度
LINE_WIDTH = 1.2         # 波形线宽

# 布局
TILE_COLS = 6            # Browse 每行格子数
VISIBLE_ROWS = 6         # Compare 一屏可见行数
VISIBLE_TILE_ROWS = 4    # Browse 一屏可见行数

# 滑动条范围
WINDOW_SEC_MIN = 0.05   # 时窗下限
WINDOW_SEC_MAX = 0.10   # 时窗上限
AMP_SCALE_MIN  = 1.0    # 幅值下限
AMP_SCALE_MAX  = 3.0    # 幅值上限
SPEED_MUL_MIN  = 0.5    # 速度下限
SPEED_MUL_MAX  = 1.5    # 速度上限

# 数据驱动
Y_PERCENTILE = 99.9      # 通道幅值百分位
SPACING_FACTOR = 3       # 通道间距系数
```

## Detail 窗口

- **触发**: 点击 Compare 或 Browse 中的任意通道
- **Overlay 模式**（默认）: 两条曲线叠加在同一 PlotItem，有图例区分 Rawdata/Recdata
- **Side-by-Side 模式**: 左右两个独立 PlotItem 并排对比
- **生命周期**: WeakSet 管理，同一通道不重复创建（激活已有窗口），关闭自动销毁
- **跟随播放**: 连接 `Player.frame_ready` 信号，每帧 `setData()` 刷新
- **仅更新可见面板**: 隐藏面板的曲线不调用 `setData()`，节省开销

## 数据加载流程

```
用户点击 "Load Rawdata (.mat)" → QFileDialog → LoaderWorker(path).start()
  → 后台线程: _load_mat_sync()
    1. 检查 .rawcache 缓存 → 有则直接 memmap（秒开）
    2. 无缓存 → scipy.loadmat（v5/v7）或 h5py（v7.3）
    3. 查找采样率（遍历 SFREQ_KEYS）
    4. 提取最大矩阵 → float32 → 写入 .rawcache → memmap
  → 主线程: finished 信号 → 填充 sd.orig → 启用 Load Recdata 按钮

用户点击 "Load Recdata (.mat)" → 同上流程
  → 通道数校验（支持自动转置）
  → 长度对齐（取较短者截断）
  → compute_params() — 前 5 秒数据计算每通道幅值（Y_PERCENTILE 分位）
  → grid.build() — 创建对象池 + 斑马纹 + 标签
  → 启用所有控件（播放按钮、4 个滑动条）
```

## 打包

```bash
pyinstaller SignalViewer.spec
# 输出: dist/SignalViewer.exe（无命令行窗口，带图标）
```

## 已知边界

- **PyQt5 限制**: `QFont.setWeight()` 不接受 CSS 权重（700），必须用 `setBold(True)` 布尔值
- **pyqtgraph 限制**: `TextItem` 和 `AxisItem.label` 不响应 QSS 样式表，必须代码设 `QFont`
- **memmap 限制**: `.rawcache` 文件必须保持与 .mat 同级目录且不被外部修改
- **键盘**: 仅 Space 一个快捷键。无 ← → ↑ ↓ PageUp PageDown 等键位
