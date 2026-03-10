#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ROOT="/tmp/mpd-streamdeck-appimage-build"
APPDIR_NAME="MPD218 Streamdeck-x86_64"
OUTPUT_NAME="mpd218-streamdeck-x86_64.AppImage"
APPIMAGETOOL="/home/masterp/.cache/python-appimage/bin/.appimagetool-continuous.appdir.x86_64/AppRun"

rm -rf "${BUILD_ROOT}"
mkdir -p "${BUILD_ROOT}"
rsync -a --delete --exclude .git "${PROJECT_ROOT}/" "${BUILD_ROOT}/"

pushd "${BUILD_ROOT}" >/dev/null
/usr/bin/uv build --wheel
env -u APPDIR -u APPIMAGE -u LD_LIBRARY_PATH /usr/bin/uv tool run --from python-appimage python-appimage build app --no-packaging -p 3.10 -n mpd218-streamdeck appimage
env -u APPDIR -u APPIMAGE -u LD_LIBRARY_PATH "${APPIMAGETOOL}" "${BUILD_ROOT}/${APPDIR_NAME}" "${BUILD_ROOT}/${OUTPUT_NAME}"
cp -f "${BUILD_ROOT}/${OUTPUT_NAME}" "${PROJECT_ROOT}/${OUTPUT_NAME}"
chmod +x "${PROJECT_ROOT}/${OUTPUT_NAME}"
popd >/dev/null

echo "Built ${PROJECT_ROOT}/${OUTPUT_NAME}"
