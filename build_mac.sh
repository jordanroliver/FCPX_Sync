#!/bin/bash
# Build FCPX Sync as a standalone macOS .app bundle using PyInstaller.
#
# Prerequisites:
#   pip install ".[build]"
#   brew install ffmpeg   (ffmpeg must be on PATH)
#
# Usage:
#   ./build_mac.sh
#
# Output:
#   dist/FCPX Sync.app

set -e

echo "Building FCPX Sync.app ..."

# Find ffmpeg so we can bundle it
FFPROBE_PATH=$(which ffprobe 2>/dev/null || true)

EXTRA_DATA=""
if [ -n "$FFPROBE_PATH" ]; then
    echo "Bundling ffprobe from: $FFPROBE_PATH"
    EXTRA_DATA="--add-binary ${FFPROBE_PATH}:."
fi

pyinstaller \
    --name "FCPX Sync" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    $EXTRA_DATA \
    --hidden-import fcpx_sync \
    --hidden-import fcpx_sync.cli \
    --hidden-import fcpx_sync.sync_engine \
    --hidden-import fcpx_sync.fcpxml \
    --hidden-import fcpx_sync.app \
    fcpx_sync/app.py

echo ""
echo "Done! App bundle at: dist/FCPX Sync.app"
echo "You can move it to /Applications or double-click to run."
