# mp218-streamdeck

Windows-first Akai MPD218 control surface built with Python, `mido`, and `python-rtmidi`.

## Features
- 3 profiles (`dev`, `ai`, `stream`)
- Full pad range support (Bank A/B/C notes 36-83)
- Profile-aware LED rendering with press feedback
- Config-driven pad and knob mappings
- Hot reload for `config.json`

## Run
- PowerShell: `.\run.ps1`
- Direct: `python controller.py --config config.json`
