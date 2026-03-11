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

### Restart
1) Stop the running process (Ctrl+C in the terminal where it is running).  
2) Start again with:
```powershell
.\run.ps1
```

## Config hot reload

`config.json` hot-reloads automatically while running.  
If behavior seems stuck, run a service/app restart using the commands above.
