# mpd-streamdeck

Config-driven Akai MPD218 control surface for Windows and Linux, built with Python.

This project turns an MPD218 into a profile-aware macro controller with LED feedback, knob actions, hot reload, and automatic profile switching based on the active foreground app.

## Highlights

- Config-driven pads/knobs with hot reload
- Full pad range support (notes `36-83`, Banks A/B/C)
- LED feedback with:
  - profile idle brightness
  - press flash + restore
  - reserved indicator pads
  - diff-based rendering (reduced flicker)
- Non-blocking press flash restore queue (no loop stall on press)
- Knob (`control_change`) action support with threshold filtering
- MIDI auto-detection for renamed MPD ports
- Context-aware profile switching on Windows (`Cursor`, `OBS`, `ChatGPT`, `Claude`, `Grok`, etc.)
- Manual profile override lock to prevent immediate context switch bounce
- Interactive HUD overlay with:
  - physical MPD218 pad orientation
  - clickable pads and command palette search
  - last-pressed pad highlight
  - pad/hotkey toggles (`51`, `67`, `83`, `Ctrl+Shift+H`)
- Hold-to-talk dictation:
  - `dictate` -> transcribe and type at cursor
  - `dictate_to_telegram` -> transcribe and send to a Telegram chat
  - `dictate_to_openclaw` -> transcribe and send through OpenClaw to Boris
  - `dictate_to_markdown` -> transcribe and append to a daily markdown note
- Current high-value pad routing in active profiles:
  - pad `78` -> `Hermes env` via `focus_or_launch` for Telegram Desktop
  - pad `79` -> `Talk to Boris` via local OpenClaw (`dictate_to_openclaw`)
  - pad `82` -> `Talk to Hermes` via the current Hermes Telegram DM (`dictate_to_telegram`)
- Optional Boris desktop voice sidecar:
  - watches local OpenClaw session JSONL logs for new Boris replies
  - dedupes spoken replies
  - speaks the full local Boris reply by default
  - keeps optional summary mode if wanted
  - speaks it locally on Windows via built-in `System.Speech`
- Markdown capture helpers:
  - `new_markdown_doc` -> create a fresh markdown doc and open it in Typora
- `key_combo` action support for desktop shortcuts
- OpenClaw / Boris environment (pad **77** in default profiles): `openclaw_smart_startup` ensures the gateway is up (start only if down), opens the Control UI via `openclaw dashboard`, brings up [ClawCommand](http://127.0.0.1:4310) in Firefox when possible, and starts `openclaw tui` only if no TUI process is already running
- Hermes launcher (pad **78** in active profiles): `focus_or_launch` brings Telegram Desktop to the front if it is already running, otherwise launches it

## Project Layout

```text
mpd-streamdeck/
  controller.py
  config.json
  run.ps1
  .env.example
  boris_voice_sidecar.py
  core/
    app.py
    boris_voice_sidecar.py
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
    telegram_sender.py
    openclaw_sender.py
    openclaw_env.py
```

## Requirements

- Windows 10/11 or Linux
- Python 3.10+
- Akai MPD218
- MPD218 pads configured on MIDI channel 10 (project uses `pad_channel: 9` because `mido` is 0-indexed)

Core Python packages:

- `mido`
- `python-rtmidi`
- `psutil`
- `pywin32`

Optional packages for dictation / speech features:

- `faster-whisper`
- `sounddevice`
- `soundfile`
- `pyperclip` (Windows clipboard paste)
- `pyautogui` (Windows key injection)

Install:

```powershell
python -m pip install -r requirements.txt
```

`faster-whisper` downloads the selected model on first use, then runs local transcription from cache.

## Secrets / Telegram setup

The project now supports a local `.env` file in the repo root. `run.ps1` loads it into the process environment before starting the controller.

Create:

```text
.env
```

Example:

```env
MPD_TELEGRAM_BOT_TOKEN=your_bot_token_here
MPD_TELEGRAM_CHAT_ID_BORIS=1636853070
```

Notes:
- `.env` is gitignored
- `.env.example` is committed as the template
- `dictate_to_telegram` can use either:
  - `chat_id` directly in the action, or
  - `destination` with an env var like `MPD_TELEGRAM_CHAT_ID_BORIS`

## Run

Preferred:

```powershell
.\run.ps1
```

Enable logon autostart on Windows:

```powershell
.\install-autostart.ps1
```

Remove logon autostart:

```powershell
.\remove-autostart.ps1
```

Direct:

```powershell
python controller.py --config config.json
```

### Boris voice sidecar (Phase 1)

This is a separate runtime component. It watches the local OpenClaw main-session logs, dedupes Boris replies, and speaks the full local reply on the Windows desktop by default. The intended path is now fully local: MPD -> OpenClaw main session -> local session log -> desktop speech. If you want the old short spoken behavior, there is also an optional summary mode.

Run it in another terminal:

```powershell
.\run-boris-voice.ps1
```

One-shot test for the latest unseen reply:

```powershell
.\run-boris-voice.ps1 -Once
```

Notes:
- Default session hint targets the local Boris main session: `agent:main:main`
- State/dedupe file: `C:\Users\theve\.openclaw\workspace\boris_voice_sidecar_state.json`
- Optional voice selection: `.\run-boris-voice.ps1 -Voice "Microsoft David Desktop"`
- Optional old short-summary mode: `.\run-boris-voice.ps1 -SpeechMode summary`

### Linux service runtime (dictation-enabled)

Use the user service with host Python so installed dictation dependencies are available:

```ini
ExecStart=/usr/bin/python3 /media/masterp/AI-Models/mpd-streamdeck/controller.py --config /media/masterp/AI-Models/mpd-streamdeck/config.json
```

If you want Telegram dictation under Linux systemd, add env vars in the service or an EnvironmentFile.

After editing the service:

```bash
systemctl --user daemon-reload
systemctl --user restart mpd-streamdeck.service
```

## Quick Start / Restart

Use `RUNME.md` for copy/paste day-to-day commands (start, restart, status, logs) on both Linux and Windows:

- `RUNME.md`

## How It Works

- The app opens MIDI input/output ports.
- It polls incoming MIDI events:
  - `note_on` -> pad press actions
  - `note_off` (and `note_on` with velocity `0`) -> pad release actions (`dictate`, `dictate_to_telegram`)
  - `control_change` -> knob actions
- It renders LEDs for the active profile.
- It polls `config.json` for changes and hot-reloads safely.
- It optionally polls the foreground process every 250ms and auto-switches profile via `context_profiles`.

## Action Types

Supported action types in pad/knob mappings:

- `cmd` - execute shell command
- `key_combo` - send a desktop key combo
- `url` - open URL in browser
- `focus_or_launch` - focus running app window or launch it if not running
- `dictate` - hold pad to record microphone input, release to transcribe and type at cursor
- `dictate_to_telegram` - hold pad to record microphone input, release to transcribe and send to Telegram
- `dictate_to_openclaw` - hold pad to record microphone input, release to transcribe and send through OpenClaw/Boris routing (local delivery skips gateway preflight; non-local channels wake the gateway if needed)
- `dictate_to_markdown` - hold pad to record microphone input, release to transcribe and append to a daily markdown file
- `openclaw_smart_startup` - one-press “smart” environment: ensure OpenClaw gateway running (no restart when healthy), open Control UI (`openclaw dashboard` — tokenized/auth handoff per OpenClaw docs), ensure ClawCommand server is listening (optional `clawcommand_dir_*`), open ClawCommand URL in Firefox (fallback: default browser), start `openclaw tui` in a new terminal only when not already running
- `new_markdown_doc` - create a new markdown document and optionally open it in Typora
- `profile` - switch active profile

Reserved-pad note:
- Pads `81`, `82`, and `83` are LED-reserved indicator pads, but the app still allows reserved pads to run dictate-style actions. That is why pad `82` can be used for `Talk to Hermes` while still living in the reserved bank.
- `toggle_flag` - toggle a runtime status flag (`obs_recording`, `mic_muted`, `docker_running`)

## Current note on Bank C 81/82

- Button `78` is now the current `Hermes env` one-press launcher.
- Button `78` focuses Telegram Desktop if it is already open, or launches it if it is not.
- Button `79` is the current `Talk to Boris` hold-to-talk route.
- Button `82` is the current `Talk to Hermes` hold-to-talk route.
- Button `82` now uses `dictate_to_telegram` and sends to the current Hermes Telegram DM.
- `81` is no longer used as the old profile-switch partner for `82` in the active Windows/Linux dev/ai/stream profiles.
- This layout is intentional so Boris and Hermes each have a dedicated hold-to-talk pad.
- `hud` - toggle the HUD overlay
- `log` - print debug/log message
- `restart` - restart the controller process
- `noop` - no operation
- `hold_double_click` - repeatedly double-click while held
- `transcribe_stream` - toggle continuous meeting transcription
- `volume_step`, `media_step`, `brightness_step`, `scroll_step`, `tab_step`, `zoom_step`

## `config.json` Reference

Top-level sections:

- `config_version`
- `midi`
- `controller`
- `led`
- `status_flags_defaults`
- `context_profiles`
- `profiles`

### `controller`

- `default_profile`: startup profile
- `hot_reload_interval_ms`: config polling interval
- `knob_change_threshold`: min CC delta to trigger knob actions
- `manual_lock_seconds`: temporary context lock duration after manual profile switch
- `hud_pad`: primary MIDI note that toggles HUD
- `hud_toggle_key`: global keyboard hotkey for HUD toggle
- `hud_duration_seconds`: auto-hide timeout for HUD overlay
- `log_midi_input`: verbose MIDI input logging toggle

### `profiles`

Each profile has:

- `pads`: map note number strings to actions
- `knobs`: map CC number strings to actions

Example Telegram dictation pad:

```json
"74": {
  "type": "dictate_to_telegram",
  "label": "Talk to Boris",
  "destination": "BORIS",
  "model": "base.en",
  "language": "en"
}
```

### `openclaw_smart_startup` (typical pad **77**)

Gateway auth and dashboard URLs are **not** duplicated in `config.json`. Set `gateway.auth.token` (or `OPENCLAW_GATEWAY_TOKEN`) in OpenClaw on the gateway host; the CLI’s `openclaw dashboard` is the supported way to open an authenticated Control UI. See [OpenClaw Dashboard](https://docs.openclaw.ai/web/dashboard).

Optional fields:

- `clawcommand_url` — default `http://127.0.0.1:4310`
- `clawcommand_dir` / `clawcommand_dir_windows` / `clawcommand_dir_linux` — project directory used to run `npm start` when the URL is not reachable
- `clawcommand_start_cmd` / `clawcommand_start_cmd_windows` / `clawcommand_start_cmd_linux` — override the start command

Example:

```json
"77": {
  "type": "openclaw_smart_startup",
  "label": "OpenClaw env (smart)",
  "clawcommand_url": "http://127.0.0.1:4310",
  "clawcommand_dir_windows": "F:\\ClawCommand"
}
```

Pad `78` is now a separate Hermes-only launcher:

```json
"78": {
  "type": "focus_or_launch",
  "label": "Hermes env",
  "process": "telegram",
  "command": "telegram-desktop",
  "command_windows": "\"C:\\Users\\theve\\AppData\\Roaming\\Telegram Desktop\\Telegram.exe\""
}
```

On Linux-only profiles, add `clawcommand_dir_linux` (or `clawcommand_dir`) if you want the controller to start ClawCommand automatically when the port is closed.

If you prefer explicit targeting instead of named destinations:

```json
"74": {
  "type": "dictate_to_telegram",
  "chat_id": "1636853070",
  "model": "base.en",
  "language": "en"
}
```

## Troubleshooting

- `ModuleNotFoundError: psutil`  
  Install context deps: `python -m pip install psutil pywin32`

- Dictation logs `missing dependencies: sounddevice/soundfile/numpy`  
  Install dictation deps: `python -m pip install -r requirements.txt`

- `dictate_to_telegram` fails with token/chat errors  
  Confirm `.env` exists and `run.ps1` is being used, or set the variables in your launcher/service environment.

- MIDI ports fail to open  
  Check available port names and adjust `midi.input_port`/`output_port`, or keep auto-detect enabled.

- Pad LEDs do not respond  
  Confirm output port is correct and `pad_channel` is `9`.

- Config change does nothing  
  Validate JSON syntax; invalid reloads are rejected and previous good config stays active.

## Safety + Reliability

- Config is validated before use.
- Hot reload keeps last known-good config on errors.
- Action failures are logged and do not crash the loop.
- LED updates are diff-based to reduce redundant MIDI traffic/flicker.
