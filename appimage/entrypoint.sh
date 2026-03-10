#!/usr/bin/env bash
set -euo pipefail

exec "${APPDIR}/opt/python{{ python-version }}/bin/mpd218_streamdeck" "$@"
