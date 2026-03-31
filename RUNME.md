# RUNME

Minimal day-to-day commands so you can run this without extra back-and-forth.

## Linux

### First-time enable autostart
```bash
systemctl --user daemon-reload
systemctl --user enable --now mpd-streamdeck.service
```

### Start now
```bash
systemctl --user start mpd-streamdeck.service
```

### Restart (after config/code updates)
```bash
systemctl --user restart mpd-streamdeck.service
```

### Check status
```bash
systemctl --user status mpd-streamdeck.service --no-pager
```

### Live logs
```bash
journalctl --user -u mpd-streamdeck.service -f
```

### Stop
```bash
systemctl --user stop mpd-streamdeck.service
```

### Disable autostart
```bash
systemctl --user disable --now mpd-streamdeck.service
```

## Windows

Run from project root (`mpd-streamdeck`).

### Enable autostart (Task Scheduler)
```powershell
.\install-autostart.ps1
```

### IMPORTANT: Dictation dependency install (Windows)
If you use the `dictate` action type, install optional dependencies first:
```powershell
python -m pip install -r requirements.txt
```
Without this, push-to-talk dictation will not start.

### Start now (preferred)
```powershell
.\run.ps1
```

### Start now (direct)
```powershell
python controller.py --config config.json
```

### Restart (script — same logic as pad 48)
```powershell
.\restart.ps1
```

### Desktop shortcut (manual restart if the pad button fails)
Run once (creates **Restart MPD Streamdeck** on your Desktop):
```powershell
.\install-desktop-restart-shortcut.ps1
```

### Restart (manual)
1) Stop the running process (Ctrl+C in the terminal where it is running).  
2) Start again with:
```powershell
.\run.ps1
```

### Disable autostart
```powershell
.\remove-autostart.ps1
```

## Config hot reload

`config.json` hot-reloads automatically while running.  
If behavior seems stuck, run a service/app restart using the commands above.

## OpenClaw pad (77) prerequisites

If you use **`openclaw_smart_startup`** (default pad 77):

- [OpenClaw CLI](https://docs.openclaw.ai/start/openclaw) on `PATH` (`openclaw`, `openclaw gateway`, `openclaw dashboard`, `openclaw tui`).
- **Firefox** if you want ClawCommand to open there; otherwise the action falls back to the default browser.
- **ClawCommand**: set `clawcommand_dir_windows` / `clawcommand_dir_linux` in the action so the controller can run `npm start` when `clawcommand_url` is not reachable.

Control UI auth: configure the gateway token in OpenClaw (`gateway.auth.token` or `OPENCLAW_GATEWAY_TOKEN`); do not store it in `config.json`. See [Dashboard / token basics](https://docs.openclaw.ai/web/dashboard).
