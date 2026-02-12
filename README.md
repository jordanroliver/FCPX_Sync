# FCPX Sync

**Free, open-source batch audio/video sync for Final Cut Pro X.**

Matches external audio recordings to video clips using waveform cross-correlation, then generates an FCPXML file with synchronized clips ready for import into Final Cut Pro.

No timecode required. No $199 license. Just works.

## What It Does

1. Scans a folder for video files (with scratch audio) and external audio files
2. Cross-correlates the audio waveforms to find which audio matches which video
3. Calculates the precise sync offset (sample-accurate)
4. Outputs an `.fcpxml` file you import into Final Cut Pro

Each matched pair becomes a **synchronized clip** in FCPX with the external audio replacing the camera audio.

## Requirements

- **Python 3.10+**
- **FFmpeg** (must be on your PATH)
- **macOS** with Final Cut Pro (for importing the result)

## Install

```bash
# Clone
git clone https://github.com/jordanroliver/FCPX_Sync.git
cd FCPX_Sync

# Install
pip install .

# Or install in dev mode
pip install -e .
```

## Usage

### Single folder (video + audio files mixed together)

```bash
fcpx-sync /path/to/your/media/
```

### Separate folders

```bash
fcpx-sync /path/to/project/ \
  --video-folder /path/to/video/ \
  --audio-folder /path/to/audio/
```

### Options

```
fcpx-sync <folder> [options]

  -o, --output PATH        Output FCPXML file path (default: <folder>/synced.fcpxml)
  --event-name NAME        Name for the FCPX event (default: "Synced Clips")
  --video-folder PATH      Separate folder for video files
  --audio-folder PATH      Separate folder for audio files
  -q, --quiet              Suppress progress output
```

### Import into Final Cut Pro

1. Run `fcpx-sync` on your media folder
2. Open Final Cut Pro
3. **File → Import → XML...**
4. Select the generated `.fcpxml` file
5. Your synchronized clips appear in a new Event

## Supported Formats

**Video:** `.mov` `.mp4` `.m4v` `.mxf` `.avi` `.mkv`

**Audio:** `.wav` `.aif` `.aiff` `.mp3` `.m4a` `.flac` `.bwf`

(Anything FFmpeg can decode)

## How It Works

The tool uses **cross-correlation** — the same technique used by professional sync tools like PluralEyes and Sync-N-Link:

1. **Extract audio** from each video file using FFmpeg
2. **Downsample** both signals to 8kHz mono (fast, plenty of detail for sync)
3. **Normalize** amplitude to prevent bias
4. **FFT cross-correlation** (via SciPy) finds the time offset where the two signals align best
5. **Peak detection** identifies the best match and sync confidence score
6. **FCPXML generation** creates `<sync-clip>` elements with the correct time offsets

## License

MIT — do whatever you want with it.
