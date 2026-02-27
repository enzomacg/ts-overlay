# TS3 Overlay

A lightweight, customizable overlay for **TeamSpeak 3** built with PySide6. Displays channel members, talking status, whisper indicators, and message toasts — all as a frameless, always-on-top transparent window.

![Overlay screenshot](docs/preview.png)

---

## Features

- **Live user list** — shows everyone in your current channel with speaking, muted and deafened indicators
- **Whisper detection** — users whispering to you are highlighted in pink with a dedicated icon; a floating whisper window tracks active whispers
- **Message toasts** — channel and private messages appear as non-intrusive popups with configurable duration and position
- **Fully positionable** — drag any window freely; use the *Preview Windows* tool to set positions visually
- **Interactive / pass-through toggle** — switch between interactive mode (movable, mouse visible) and full pass-through (clicks go straight to the game)
- **Real-time settings** — opacity, font size and background dim update live as you move the sliders
- **Color picker** — choose accent, join, leave and move colors via a native color dialog
- **Hotkeys** — configurable global hotkeys for toggle, config, notifications and quit
- **System tray** — minimize to tray, quick access menu
- **Auto-reconnect** — reconnects automatically if TS3 closes or crashes

---

## Requirements

- Windows 10 / 11
- Python 3.11+ (3.14 tested)
- TeamSpeak 3 client with **ClientQuery plugin** enabled

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Enable ClientQuery in TeamSpeak 3

1. Open TeamSpeak 3
2. Go to **Tools → Addons → Plugins**
3. Enable **ClientQuery**
4. Note your **API key** from `Tools → Addons → ClientQuery → Settings`

### 3. Run

```bash
python overlay_dp.py
```

On first launch a dialog will ask for your API key and port (default `25639`).

---

## Icons (optional)

Place `.png` icon files in an `icons/` folder next to the script. Supported names:

| File | Used for |
|------|----------|
| `speaking.png` | User is talking |
| `muted.png` | User is muted |
| `deaf.png` | User is deafened |
| `whisp.png` | Whisper indicator |

Icons are scaled to 14×16 px. If a file is missing, a text fallback is used automatically.

---

## Building a standalone .exe

```bash
pyinstaller --onefile --windowed --name "TS3Overlay" overlay_dp.py
```

> The warnings about `fbclient.dll`, `OCI.dll`, `LIBPQ.dll` etc. during build are harmless — they are unused SQL driver dependencies from PySide6 that are not present on most systems.

Add your icons folder:

```bash
pyinstaller --onefile --windowed --name "TS3Overlay" --add-data "icons;icons" overlay_dp.py
```

---

## Configuration

Settings are saved to `~/.ts3overlay_config.json` and can be edited via the config panel (right-click the overlay or press `F10`).

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | `""` | ClientQuery API key |
| `port` | `25639` | ClientQuery TCP port |
| `opacity` | `0.90` | Window opacity (0.1–1.0) |
| `font_size` | `10` | User name font size |
| `bg_dim` | `0.0` | Background dimming (0–0.8) |
| `hotkey` | `f9` | Toggle overlay visibility |
| `hotkey_config` | `f10` | Open settings |
| `hotkey_notifications` | `f8` | Toggle notifications window |
| `click_through` | `false` | Interactive mode (drag enabled) |
| `hide_alone` | `true` | Hide when alone in channel |
| `pulse_on_talk` | `true` | Pulse accent dot when someone talks |

---

## Hotkey format

Single key: `f9`, `f10`, `pause`  
Modifier combo: `ctrl+shift+o`, `alt+f1`

---

## License

MIT
