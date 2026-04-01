# MPD218 Handoff

## Project
- Repo: `F:\mpd-streamdeck`
- Purpose: config-driven Akai MPD218 macro/controller app for Windows + Linux.

## Relevant files
- `config.json` — pad/knob mappings
- `core/app.py` — MIDI press/release flow
- `core/action_runner.py` — action dispatch (includes `openclaw_smart_startup`)
- `core/openclaw_env.py` — ClawCommand probe/start, `openclaw tui` detection/spawn
- `core/dictation_service.py` — hold-to-talk recording/transcription
- `core/openclaw_sender.py` — Boris input via OpenClaw; gateway ensure; `openclaw dashboard` Control UI
- `core/boris_voice_sidecar.py` — new Phase 1 desktop voice watcher/speaker
- `boris_voice_sidecar.py` — simple entrypoint
- `run-boris-voice.ps1` — Windows launcher for the sidecar
- `run.ps1` — controller launcher
- `.env` / `.env.example` — local env support

## Current status
- **Pad 77** (`openclaw_smart_startup`): smart startup for OpenClaw + ClawCommand + TUI — gateway start only if down, `openclaw dashboard` for Control UI, Firefox (or fallback) for ClawCommand URL, new TUI terminal only if none running.
- **Bank C pads 81 and 82**: temporarily removed from the active Windows/Linux dev/ai/stream profiles so they can be repurposed for new actions.
- Boris dictation input path remains intact: MPD hold-to-talk -> transcribe -> OpenClaw send.
- The `Talk to Boris` send path now uses the intended **local OpenClaw main session** instead of the old Telegram direct-delivery route.
- Added a Boris desktop voice sidecar that uses the local session logs already available on disk:
  - `C:\Users\theve\.openclaw\agents\main\sessions\*.jsonl`
  - `C:\Users\theve\.openclaw\agents\main\sessions\sessions.json`
- The sidecar:
  - resolves `agent:main:main` through the session index first
  - watches for new assistant messages
  - dedupes using a persisted state file
  - strips reply markers / markdown-ish noise
  - speaks the full cleaned local Boris reply by default
  - still supports short summary mode if desired
  - speaks it locally on Windows with built-in `System.Speech.Synthesis.SpeechSynthesizer`
- Telegram is no longer part of the primary `Talk to Boris` path.

## How to run
Controller:
```powershell
cd F:\mpd-streamdeck
.\run.ps1
```

Voice sidecar:
```powershell
cd F:\mpd-streamdeck
.\run-boris-voice.ps1
```

One-shot latest unseen reply:
```powershell
.\run-boris-voice.ps1 -Once
```

Optional voice:
```powershell
.\run-boris-voice.ps1 -Voice "Microsoft David Desktop"
```

## Notes
- Sidecar dedupe state lives at:
  - `C:\Users\theve\.openclaw\workspace\boris_voice_sidecar_state.json`
- Default session hint is:
  - `agent:main:main`
- No extra TTS dependency was added; Phase 1 uses the shortest reliable built-in Windows path.

## What remains
1. Real-world validation against live Boris replies to confirm the session-hint targeting is always correct.
2. Optionally narrow reply summarization heuristics if spoken summaries feel too long/too terse.
3. Optional future autostart integration if the sidecar should launch alongside the controller every time.
4. Optional direct Telegram polling fallback only if local session logs prove unreliable.
