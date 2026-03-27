# MPD218 Handoff

## Project
- Repo: `F:\mpd-streamdeck`
- Purpose: config-driven Akai MPD218 macro/controller app for Windows + Linux.

## Relevant files
- `config.json` — pad/knob mappings
- `core/app.py` — MIDI press/release flow
- `core/action_runner.py` — action dispatch
- `core/dictation_service.py` — hold-to-talk recording/transcription
- `core/telegram_sender.py` — Telegram send support for Boris dictation
- `run.ps1` — now loads `.env`
- `.env` / `.env.example` — Telegram secrets

## Current status
- Boris dictation now uses `dictate_to_openclaw` for pad 79 so Boris input routes through OpenClaw instead of raw Telegram bot send.
- Extra confirmation added for pad 79:
  - explicit `[boris] ...` log lines
  - desktop popup when transcript is heard/sent (Windows MessageBox, Linux `notify-send`)
- `openclaw_sender.py` now resolves the real OpenClaw executable path and auto-starts the gateway if it is asleep before retrying delivery.
- Legacy `dictate_to_telegram` still exists in code but is no longer the primary Boris path.
- Markdown capture actions now exist:
  - `dictate_to_markdown` = hold-to-talk append into daily markdown note
  - `new_markdown_doc` = create standalone markdown file and open in Typora
- Current pad cluster across all profiles:
  - `73` = new markdown doc in `F:\notes\ideas` (opens in Typora)
  - `74` = daily idea capture in `F:\notes\ideas\YYYY-MM-DD.md`
  - `77` = list Boris/OpenClaw threads (`openclaw sessions`)
  - `78` = Boris thread UI (`openclaw tui`)
  - `79` = Talk to Boris (`dictate_to_openclaw`)
- This is a practical CLI-driven implementation, not a deep session-API integration.

## Notes
- `openclaw sessions` is a clear "list threads" command.
- There was no obvious simple CLI subcommand found for "create new Boris thread" directly, so `openclaw tui` is used as the nearest practical thread-management entry point.
- If future work wants true one-button "new Boris thread", inspect newer OpenClaw CLI/session APIs or use a custom action path.

## Next steps
1. Restart controller: `cd F:\mpd-streamdeck && .\restart.ps1`
2. Test pads 77/78/79 in current Windows profile.
3. If desired, refine 78 from `openclaw tui` to a more direct Boris/new-session flow once a reliable CLI/API path is identified.
4. Optionally free/reassign pad 74 now that 79 owns Boris dictation.
