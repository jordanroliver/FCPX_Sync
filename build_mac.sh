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

# --- Generate app icon ---
echo "Generating icon..."
python make_icon.py

# Convert PNG to .icns using macOS tools
mkdir -p icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png      >/dev/null
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png   >/dev/null
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png      >/dev/null
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png   >/dev/null
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png    >/dev/null
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png >/dev/null
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png    >/dev/null
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png >/dev/null
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png    >/dev/null
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png >/dev/null
iconutil -c icns icon.iconset -o icon.icns
rm -rf icon.iconset icon.png
echo "Icon ready: icon.icns"

# --- Find ffprobe to bundle ---
FFPROBE_PATH=$(which ffprobe 2>/dev/null || true)

EXTRA_DATA=""
if [ -n "$FFPROBE_PATH" ]; then
    echo "Bundling ffprobe from: $FFPROBE_PATH"
    EXTRA_DATA="--add-binary ${FFPROBE_PATH}:."
fi

# --- Build ---
pyinstaller \
    --name "FCPX Sync" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --icon icon.icns \
    $EXTRA_DATA \
    --hidden-import fcpx_sync \
    --hidden-import fcpx_sync.cli \
    --hidden-import fcpx_sync.sync_engine \
    --hidden-import fcpx_sync.fcpxml \
    --hidden-import fcpx_sync.app \
    fcpx_sync/app.py

rm -f icon.icns

echo ""
echo "Done! App bundle at: dist/FCPX Sync.app"
echo "You can move it to /Applications or double-click to run."
