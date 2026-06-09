# SignalViewer — Original vs Reconstructed Neural Signal Comparison Viewer

2048-channel side-by-side neural signal comparator with 5 display modes, 60fps performance.

## Project Structure

```
SignalViewer/
├── main.py              Entry point
├── config.py            Parameters, color scheme (Minimalist Industrial), stylesheet
├── data.py              File loading (.mat) + SignalData with memmap support
├── decimator.py         LTTB + Min-Max downsampling
├── player.py            Playback engine (PreciseTimer, 60fps)
├── grid.py              Grid view — Row mode + Tile mode (chunked rendering)
├── detail.py            Detail window — Overlay + Side-by-side modes
├── oscilloscope.py      Oscilloscope scrolling mode
├── app.py               Main window — controls + waveform area + 4 sliders
├── utils.py             Shared utilities (font, pen factories)
├── logo.ico             Application icon
├── SignalViewer.spec    PyInstaller configuration
└── pack_env/            Python virtual environment
```

## Module Dependencies

```
config ──────────────────────────────────────────┐
   │                                               │
   ├── decimator ─────────────────────────────────┤
   │       │                                       │
   ├── data (memmap) ─────────────────────────────┤
   │       │                                       │
   │       ├── player ────────────────────────────┤
   │       │       │                               │
   │       ├── grid (row/tile) ───────────────────┤
   │       │       │                               │
   │       ├── oscilloscope ──────────────────────┤
   │       │       │                               │
   │       ├── detail (overlay) ──────────────────┤
   │       │       │                               │
   └───────┴───────┴── app ──── main
```

## Display Modes

| Mode | Description |
|------|-------------|
| **Row** | One channel per row, left=original (white), right=reconstructed (yellow) |
| **Tile** | 6 tiles per row, left grid=original, right grid=reconstructed |
| **Scope** | Oscilloscope-style scrolling waveform, 8-16 channels |
| **Detail** | Single channel zoomed view, overlay or side-by-side |
| **Overlay** | Original + reconstructed overlaid on the same axis (in Detail view) |

## Data Flow

```
.mat file → numpy.memmap → SignalData → LTTB Decimation → GPU (pyqtgraph) → Screen
```

## Keyboard Shortcuts

| Key | Function |
|-----|----------|
| `Space` | Play / Pause |
| `↑` / `↓` | Scroll channels up/down |
| `←` / `→` | Nudge time axis |
| `Ctrl+↑` / `Ctrl+↓` | Speed up / slow down |
| `Ctrl+R` | Cycle display mode |

## Controls

| Control | Range | Function |
|---------|-------|----------|
| Time Window slider | 10ms – 200ms | Horizontal zoom |
| Amplitude slider | 0.2× – 5.0× | Vertical scale |
| Speed slider | 0.1× – 10.0× | Playback speed |
| Channel slider (vertical) | | Scroll through channels |

## Color Scheme — Minimalist Industrial

| Element | Color | HEX |
|---------|-------|-----|
| Canvas background | Extreme dark | `#0A0A0A` |
| Original signal | Pure white | `#FFFFFF` |
| Reconstructed signal | Bright yellow | `#FFD600` |
| Grid lines / ticks | Very dark gray | `#262626` |
| Interactive / accent | Orange-red | `#FF4500` |
| Text | Neutral gray | `#A0A0A0` |

## 2048-Channel Performance

| Layer | Technique |
|-------|-----------|
| **Data** | `numpy.memmap` — avoids loading full matrix into RAM |
| **Compute** | LTTB downsampling — 30k points → ~1500 per channel |
| **Render** | Viewport culling — only visible channels rendered |
| **Render** | pyqtgraph GPU-accelerated curve drawing |
| **Cache** | Static layers (grid, labels) set once, not redrawn |
| **Thread** | QThread background loading — UI never blocks |
| **Objects** | Curve reuse pool — no allocation during scroll |

## Running

```bash
pack_env\Scripts\activate
python main.py
```

## Building

```bash
pyinstaller SignalViewer.spec
```
