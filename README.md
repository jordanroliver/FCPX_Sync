# FCPX Sync

**Free, open-source batch audio/video sync for Final Cut Pro X.**

Matches external audio recordings to video clips by timecode, then generates an FCPXML file with synchronized clips ready for import into Final Cut Pro.

No $199 Sync-N-Link license. Zero Python dependencies. Just FFmpeg and go.

## What It Does

1. Reads embedded timecode from your video files and audio files
2. Matches pairs by overlapping timecode ranges
3. Calculates the precise sync offset from the timecode difference
4. Outputs an `.fcpxml` file with one **synchronized clip** per pair

Each synced clip appears in FCPX as a single clip in your Event browser — video + external audio locked together.

## Requirements

- **Python 3.9+** (macOS ships with 3.9)
- **FFmpeg** (`brew install ffmpeg`)
- **macOS** with Final Cut Pro (for importing the result)
- Video and audio files must have **embedded timecode** (jam-synced on set)

## Install

```bash
git clone https://github.com/jordanroliver/FCPX_Sync.git
cd FCPX_Sync
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

## Usage

### GUI (recommended)

```bash
fcpx-sync-gui
```

A window opens with two folder pickers (Video Folder, Audio Folder) and a Sync button. Select your folders, click Sync, import the resulting `.fcpxml` into FCPX.

### Command Line

```bash
fcpx-sync /path/to/video/ /path/to/audio/
```

### Options

```
fcpx-sync <video_folder> <audio_folder> [options]

  -o, --output PATH        Output FCPXML file path (default: <video_folder>/synced.fcpxml)
  --event-name NAME        Name for the FCPX event (default: "Synced Clips")
  -q, --quiet              Suppress progress output
```

### Import into Final Cut Pro

1. Run `fcpx-sync` or `fcpx-sync-gui`
2. Open Final Cut Pro
3. **File → Import → XML...**
4. Select the generated `.fcpxml` file
5. Synchronized clips appear in a new Event

## Supported Formats

**Video:** `.mov` `.mp4` `.m4v` `.mxf` `.avi` `.mkv` `.r3d` `.braw`

**Audio:** `.wav` `.aif` `.aiff` `.mp3` `.m4a` `.flac` `.bwf`

(Anything FFmpeg can read timecode from)

## How It Works

1. **ffprobe** reads timecode metadata from each video and audio file
2. **Timecode overlap** matching pairs files whose TC ranges overlap
3. **Offset calculation** from the difference between start timecodes
4. **FCPXML generation** creates `<sync-clip>` elements with correct offsets
5. **Import** into FCPX produces synchronized clips in your Event browser

## License

MIT — do whatever you want with it.
