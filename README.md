# mp218-streamdeck

Config-driven Akai MPD218 control surface for Windows and Linux, built with Python.

This project turns an MPD218 into a profile-aware macro controller with LED feedback, knob actions, hot reload, and automatic profile switching based on the active foreground app.

## Highlights

- 3 profiles: `dev`, `ai`, `stream`
- Full pad range support (notes `36-83`, Banks A/B/C)
- LED feedback with:
  - profile idle brightness
  - press flash + restore
  - reserved indicator pads
  - diff-based rendering (reduced flicker)
- Non-blocking press flash restore queue (no loop stall on press)
- Knob (`control_change`) action support with threshold filtering
- Hot reload for `config.json` (no restart needed for config edits)
- MIDI auto-detection for renamed MPD ports
- Context-aware profile switching on Windows (`Cursor`, `OBS`, `ChatGPT`, `Claude`, `Grok`, etc.)
- Manual profile override lock to prevent immediate context switch bounce
- Interactive HUD overlay with:
  - physical MPD218 pad orientation
  - clickable pads and command palette search
  - last-pressed pad highlight
  - pad/hotkey toggles (`51`, `67`, `83`, `Ctrl+Shift+H`)

## Project Layout

```text
mpd-streamdeck/
  controller.py
  config.json
  run.ps1
  core/
    app.py
    config_loader.py
    midi_manager.py
    led_manager.py
    action_runner.py
    profile_manager.py
    state_manager.py
    hot_reload.py
    platform_utils.py
    context_manager.py
    hud_manager.py
```

## Requirements

- Windows 10/11 or Linux
- Python 3.10+
- Akai MPD218
- MPD218 pads configured on MIDI channel 10 (project uses `pad_channel: 9` because `mido` is 0-indexed)

Python packages:

- `mido`
- `python-rtmidi`
- `psutil`
- `pywin32`

Install in your venv:

```powershell
python -m pip install mido python-rtmidi psutil pywin32
```

## Run

Preferred:

```powershell
.\run.ps1
```

Direct:

```powershell
python controller.py --config config.json
```

## Quick Start / Restart

Use `RUNME.md` for copy/paste day-to-day commands (start, restart, status, logs) on both Linux and Windows:

- `RUNME.md`

## How It Works

- The app opens MIDI input/output ports.
- It polls incoming MIDI events:
  - `note_on` -> pad actions
  - `control_change` -> knob actions
- It renders LEDs for the active profile.
- It polls `config.json` for changes and hot-reloads safely.
- It optionally polls the foreground process every 250ms and auto-switches profile via `context_profiles`.

## Action Types

Supported action types in pad/knob mappings:

- `cmd` - execute shell command
- `url` - open URL in browser
- `focus_or_launch` - focus running app window or launch it if not running
- `profile` - switch active profile
- `toggle_flag` - toggle a runtime status flag (`obs_recording`, `mic_muted`, `docker_running`)
- `hud` - toggle the HUD overlay
- `log` - print debug/log message
- `noop` - no operation
- `volume_step` - placeholder hook in `platform_utils.py`

## `config.json` Reference

Top-level sections:

- `config_version`
- `midi`
- `controller`
- `led`
- `status_flags_defaults`
- `context_profiles`
- `profiles`

### `config_version`

- `1`: current supported schema version

### `midi`

- `input_port` / `output_port`: expected MPD port names
- `auto_detect_ports`: if true, fallback matching can recover renamed ports
- `auto_detect_match`: substring used for port auto-match (default `MPD218`)
- `pad_channel`: use `9` for hardware channel 10
- `pad_note_range`: min/max pad notes

### `controller`

- `default_profile`: startup profile
- `hot_reload_interval_ms`: config polling interval
- `knob_change_threshold`: min CC delta to trigger knob actions
- `manual_lock_seconds`: temporary context lock duration after manual profile switch
- `hud_pad`: primary MIDI note that toggles HUD
- `hud_toggle_key`: global keyboard hotkey for HUD toggle
- `hud_duration_seconds`: auto-hide timeout for HUD overlay
- `log_midi_input`: verbose MIDI input logging toggle

### `led`

- `pressed_brightness`: flash brightness on pad press
- `press_flash_seconds`: flash duration before restore
- `profile_idle_brightness`: base brightness per profile
- `bank_brightness_multipliers`: A/B/C relative brightness
- `indicator_pads`: profile indicator pads
- `reserved_pads`: pads excluded from macro rendering
- `animations`: startup/profile-switch animation toggles and timings

### `hud`

- `enabled`: enable/disable HUD system
- `width`: HUD window width
- `height`: HUD window height
- `opacity`: HUD transparency (0-1)

### `context_profiles`

Maps foreground process name substrings (case-insensitive) to profiles.
First match wins.

Example:

```json
"context_profiles": {
  "cursor": "dev",
  "obs": "stream",
  "chatgpt": "ai",
  "claude": "ai",
  "grok": "ai",
  "gemini": "ai",
  "webcatalog": "ai"
}
```

### `profiles`

Each profile has:

- `pads`: map note number strings to actions
- `knobs`: map CC number strings to actions

Current AI pad examples:

- `36`: `focus_or_launch` ChatGPT
- `37`: `focus_or_launch` Claude
- `38`: `focus_or_launch` Grok
- `39`: `cursor`
- `40`: `focus_or_launch` Chrome (Gemini URL)
- `41`: `start stabilitymatrix`

Bank C (`68-72`) is configured as a universal launcher bank across all profiles:

- `68`: ChatGPT
- `69`: Claude
- `70`: Grok
- `71`: Cursor
- `72`: Stability Matrix

HUD toggle pads are mapped in all profiles:

- `51` (Bank A top-right)
- `67` (Bank B top-right)
- `83` (Bank C top-right)

If an app command is not in PATH, replace with full executable path.

## Context Switching Notes

- Requires `psutil` and `pywin32`.
- Uses Windows foreground window process detection.
- Safe by design: detection failures are ignored (controller loop keeps running).
- Manual profile switching (pad actions) still works and remains authoritative.
- After manual profile switching, context auto-switching is temporarily locked for `manual_lock_seconds`.
- `focus_or_launch` first attempts to focus an existing process; if focus fails, it falls back to launch.

## HUD Notes

- HUD runs in its own thread and does not block the MIDI loop.
- Grid orientation mirrors hardware layout:
  - top row is highest notes (`48-51` on Bank A)
  - bottom row is lowest notes (`36-39` on Bank A)
- Last pressed pad is highlighted briefly (~300ms).
- Clicking a HUD pad triggers the same action as physical pad press.

## Troubleshooting

- `ModuleNotFoundError: psutil`  
  Install context deps: `python -m pip install psutil pywin32`

- MIDI ports fail to open  
  Check available port names and adjust `midi.input_port`/`output_port`, or keep auto-detect enabled.

- Pad LEDs do not respond  
  Confirm output port is correct and `pad_channel` is `9`.

- App command does not launch  
  Replace `cmd` value with a command available in PATH or full executable path.

- Config change does nothing  
  Validate JSON syntax; invalid reloads are rejected and previous good config stays active.

## Safety + Reliability

- Config is validated before use.
- Hot reload keeps last known-good config on errors.
- Action failures are logged and do not crash the loop.
- LED updates are diff-based to reduce redundant MIDI traffic/flicker.
