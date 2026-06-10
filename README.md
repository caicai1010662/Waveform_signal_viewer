# SignalViewer — 2048 通道神经信号对比查看器

原始信号 vs 重建信号并排对比。VS Code 深色主题。支持 2048 通道 @ 30k Sa/s，60fps。

## 快速开始

```bash
pack_env\Scripts\activate
python main.py
```

## 操作方式

### 按钮

| 按钮 | 功能 |
|------|------|
| **Load Rawdata** | 加载原始信号 .mat 文件 |
| **Load Recdata** | 加载重建信号 .mat 文件 |
| **Compare** | 行模式 — 一行一个通道，逐行仔细对比 |
| **Browse** | 栅格模式 — 6 列栅格，快速浏览大量通道 |
| **Roll** | 示波器模式 — 波形滚动播放 |
| **Start / Pause** | 播放 / 暂停 |
| **Loop / Once** | 循环模式开关（默认：Loop 循环播放） |

### 滑动条

| 滑动条 | 位置 | 控制内容 |
|--------|------|----------|
| **Time** | 顶部水平 | 时间窗口缩放 |
| **Amp** | 顶部水平 | 幅值纵向缩放 |
| **Speed** | 顶部水平 | 播放速度 |
| **Channel** | 右侧垂直 | 通道上下浏览 |

### 键盘与鼠标

| 操作 | 功能 |
|------|------|
| `Space` | 播放 / 暂停 |
| 鼠标点击通道波形 | 弹出该通道的详情窗口 |

## 四种显示模式

| 模式 | 说明 |
|------|------|
| **Compare（对比）** | 一行一个通道，左边原始信号，右边重建信号。适合逐通道仔细对比。 |
| **Browse（浏览）** | 每行 6 个栅格，左侧原始栅格 + 右侧重建栅格。适合快速扫览。 |
| **Roll（滚动）** | 传统示波器风格，波形从左往右滚。8 个通道堆叠显示。 |
| **Detail（详情）** | 点击通道弹出的独立窗口。支持叠加对比和左右并排两种子模式。 |

## 项目结构

```
SignalViewer/
├── main.py              程序入口
├── config.py             ⭐ 所有可调参数、配色、样式表
├── data.py               .mat 加载 + SignalData 容器（memmap 缓存）
├── decimator.py          LTTB + Min-Max 降采样算法
├── player.py             播放引擎（60fps、循环模式）
├── grid.py               网格视图 — Compare / Browse 模式（对象池 + 视口剔除）
├── detail.py             详情窗口 — 叠加 / 并排切换
├── oscilloscope.py       示波器模式（Roll）
├── app.py                主窗口 — 控件、滑动条、布局
├── utils.py              字体工厂、画笔工厂
├── logo.ico              应用图标
├── SignalViewer.spec     PyInstaller 打包配置
├── .gitignore
├── sample_data/          测试数据
└── pack_env/             Python 虚拟环境
```

## 性能设计

| 层面 | 技术 |
|------|------|
| **曲线数量** | 对象池 — 每侧仅 6~8 条可见曲线（不是 2048 条） |
| **每曲线数据量** | 窗口裁剪 — 仅 ~1500 个点（不是全量时间序列） |
| **内存** | `numpy.memmap` — .rawcache 缓存，避免全量加载到 RAM |
| **加载** | QThread 后台线程 — UI 永不阻塞 |
| **GPU** | `antialias=False` — 减少着色器开销 |

## 打包为 EXE

```bash
pyinstaller SignalViewer.spec
# 输出: dist/SignalViewer.exe
```
