# SignalViewer — 2048-Channel Neural Signal Comparison Viewer

Side-by-side comparison of original vs reconstructed neural signals.  
Supports 2048 channels @ 30k Sa/s, 5 display modes, viewport culling, looping playback.

## Quick Start

```bash
pack_env\Scripts\activate
python main.py
```

## Project Structure

```
SignalViewer/
├── main.py              Entry point (creates QApplication + MainWindow)
├── config.py            ⭐ All tunable parameters, colors, stylesheet
├── data.py              .mat loading + SignalData container (.rawcache + memmap)
├── decimator.py         LTTB + Min-Max downsampling (unused in hot path)
├── player.py            Playback engine (60fps, loop mode)
├── grid.py              Grid view — Row mode + Tile mode (object pool + window clipping)
├── detail.py            Detail window — Overlay / Side-by-side toggle
├── oscilloscope.py      Oscilloscope scrolling mode
├── app.py               Main window — controls, sliders, keyboard shortcuts
├── utils.py             Font & pen factories
├── logo.ico             App icon
├── SignalViewer.spec    PyInstaller build config
├── .gitignore
├── sample_data/         Test .mat files
└── pack_env/            Python virtual environment
```

## Display Modes

| Mode | What You See | How It Works |
|------|-------------|--------------|
| **Row** | One channel per row. Left = original (white), Right = reconstructed (yellow). 8 rows visible. | Object pool of 16 curves (8×2). Each curve holds only the current time window's data. Scroll rebinds channels. |
| **Tile** | 6 tiles per row per side. 4 rows visible = 24 tiles/side. | Same pool approach. Each tile is a mini PlotItem. |
| **Scope** | Traditional oscilloscope. 8 channels stacked, waveform scrolls. | Dedicated per-frame setData for visible channels. |
| **Detail** | Single channel, large view. Toggle overlay ↔ side-by-side. | 1 channel, 2 curves. Per-frame setData of current window. |

## Controls

### Buttons

| Button | Action |
|--------|--------|
| **Load Original** | Select original .mat file |
| **Load Reconstructed** | Select reconstructed .mat file |
| **Row / Tile / Scope** | Switch display mode (exclusive) |
| **Start /Pause** | Toggle playback |
| **Loop / One-Shot** | Toggle loop mode (default: loop) |

### Sliders

| Slider | Range | What It Controls |
|--------|-------|------------------|
| **Time Window** (horizontal, top) | 10ms – 200ms | X-axis zoom. Smaller = zoom in, see more detail. Larger = see more context. |
| **Amplitude** (horizontal, top) | 0.2× – 5.0× | Y-axis scale. 0.2× = waveforms compressed. 5.0× = waveforms expanded. |
| **Speed** (horizontal, top) | 0.1× – 10.0× | Playback speed multiplier. |
| **Channel** (vertical, right edge) | 0 – N | Scroll through channels. Drag to browse. |

### Keyboard Shortcuts

| Key | Function |
|-----|----------|
| `Space` | Play / Pause |
| `↑` / `↓` | Scroll channels (1 step) |
| `←` / `→` | Nudge time axis (5% window) |
| `Ctrl+↑` / `Ctrl+↓` | Speed up / slow down |
| `Ctrl+R` | Cycle display mode (Row → Tile → Scope → Row) |

---

## ⭐ Tuning Guide — config.py

All tunable parameters live in one file: [config.py](config.py).  
Edit → save → restart the app. Effects take effect on next data load.

### Display Parameters

```python
WINDOW_SEC = 0.05       # Default time window (seconds). 0.05 = 50ms on screen
TARGET_FPS = 60          # Target frames per second for playback
PLAYBACK_SPEED = 0.005   # Base playback speed (data seconds per real second). 0.005 = 1s data takes 200s real time at 1×
LINE_WIDTH = 0.6         # Waveform line thickness (pixels)
```

| Param | Effect of Increasing | Effect of Decreasing |
|-------|---------------------|---------------------|
| `WINDOW_SEC` | See more time context; waveform appears more compressed | See finer time detail; waveform stretches |
| `TARGET_FPS` | Smoother playback; higher CPU/GPU load | Choppier but less resource usage |
| `PLAYBACK_SPEED` | Faster base speed; slider multiplier scales from this | Slower base speed |
| `LINE_WIDTH` | Thicker, bolder waveforms | Thinner, finer waveforms |

### Grid Layout

```python
TILE_COLS = 6            # Tiles per row in Tile mode
VISIBLE_ROWS = 8         # Visible rows in Row mode (determines curve pool size)
VISIBLE_TILE_ROWS = 4    # Visible rows in Tile mode
```

| Param | Effect | Low-End Machine |
|-------|--------|-----------------|
| `VISIBLE_ROWS` | More rows = see more channels at once, but more curves in pool | **Reduce to 4-6** |
| `TILE_COLS` | More columns in Tile mode | Reduce to 4 |
| `VISIBLE_TILE_ROWS` | More tile rows | **Reduce to 2-3** |

### Performance Tuning

```python
MAX_POINTS_PER_CURVE = 6000  # (in grid.py) Max data points per curve. Beyond this, decimation kicks in.
```

This is the single most impactful performance parameter.  
Default `window_sec * s_freq = 0.05 * 30000 = 1500` points — well under the cap.

If you increase `WINDOW_SEC` to 0.2s → 6000 points → still under cap.  
Beyond 0.2s → auto-decimation engages (takes every Nth sample).

### Amplitude Calculation

```python
Y_PERCENTILE = 99.5       # Percentile for channel amplitude estimation
SPACING_FACTOR = 3.2      # Vertical spacing between channels = amp × factor
```

| Param | Effect of Increasing | Effect of Decreasing |
|-------|---------------------|---------------------|
| `Y_PERCENTILE` | More channels fit cleanly; fewer clipped peaks | More peaks visible; channels may overlap |
| `SPACING_FACTOR` | More vertical space between channels | Tighter stacking; more channels visible per screen |

### Slider Ranges

```python
WINDOW_SEC_MIN = 0.01     # Minimum time window (10ms)
WINDOW_SEC_MAX = 0.20     # Maximum time window (200ms)
AMP_SCALE_MIN  = 0.2      # Minimum amplitude (compressed)
AMP_SCALE_MAX  = 5.0      # Maximum amplitude (expanded)
SPEED_MUL_MIN  = 0.1      # Slowest playback
SPEED_MUL_MAX  = 10.0     # Fastest playback
```

### Color Scheme — Minimalist Industrial

```python
COLOR_BG       = "#0A0A0A"   # Canvas background — extreme dark
COLOR_ORIG     = "#FFFFFF"   # Original signal — pure white
COLOR_RECON    = "#FFD600"   # Reconstructed signal — bright yellow
COLOR_GRID     = "#262626"   # Grid lines / ticks
COLOR_ACCENT   = "#FF4500"   # Interactive elements / hover / click
COLOR_TEXT     = "#A0A0A0"   # All text
COLOR_CARD     = "#0F0F12"   # Panel / card backgrounds
COLOR_SEP      = "#1F1F24"   # Separator lines
COLOR_SLIDER   = "#2A2A30"   # Slider groove
COLOR_HOVER    = "#353540"   # Button hover state
```

Quick themes — just swap these colors:

| Theme | `COLOR_BG` | `COLOR_ORIG` | `COLOR_RECON` |
|-------|-----------|-------------|---------------|
| **Minimalist Industrial** (current) | `#0A0A0A` | `#FFFFFF` | `#FFD600` |
| Light mode | `#F5F5F5` | `#1A1A1A` | `#D4380D` |
| Dark blue | `#0D1117` | `#58A6FF` | `#F78166` |
| Green CRT | `#0C0C0C` | `#00FF41` | `#FFD700` |

### Font

```python
FONT_FAMILY = "Times New Roman"
FONT_SIZE   = 11
FONT_SIZE_SMALL = 9
```

## Architecture Notes for Developers

### Data Flow (Current Implementation)

```
.mat file
    │  First load: scipy/h5py → numpy array → write .rawcache → np.memmap
    │  Subsequent: np.memmap directly from .rawcache (zero RAM)
    ▼
SignalData.orig / .recon  (memmap, (2048, N) float32)
    │
    │  compute_params(): percentile(|channel[:5s]|, 99.5) → ch_amp
    ▼
GridView._fill_row_data(ptr)
    │  For each visible channel i (0..VISIBLE_ROWS-1):
    │    ch = _ch_offset + i
    │    data = memmap[ch, ptr:ptr+window_pts]   ← only ~1500 points
    │    curve[i].setData(t, data + y_offset)
    ▼
GPU → Screen
```

### Key Design Decisions

1. **Object Pool, not One-Curve-Per-Channel**: Only `VISIBLE_ROWS × 2` curves exist. On scroll, curves are rebound to new channels. This is the single biggest performance win.

2. **Window Clipping, not Full Time Series**: Each curve only holds `window_pts` (~1500) data points, never the full 300k+ time series. Scroll = reload from memmap. Playback = per-frame setData.

3. **memmap for Memory, not for Speed**: memmap prevents RAM exhaustion on large files. It does NOT make rendering faster — the viewport culling and window clipping do that.

4. **Per-Frame setData for Playback**: Replaced the old "ViewBox translation" approach. Now each frame writes fresh data. With 16 curves × 1500 points = 24k floats, this costs ~96KB per frame — negligible even on integrated graphics.

5. **No LTTB in Hot Path**: The LTTB decimator exists in `decimator.py` as a utility, but is not used during normal playback. Window clipping naturally limits point count to ~1500 (matching screen resolution). A simple `[::step]` subsampler kicks in only when points exceed `MAX_POINTS_PER_CURVE`.

## Building EXE

```bash
pyinstaller SignalViewer.spec
# Output: dist/SignalViewer.exe
```
