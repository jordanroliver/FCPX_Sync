"""Command-line interface for FCPX Sync."""

import argparse
import sys
from pathlib import Path

from .sync_engine import match_files
from .fcpxml import generate_fcpxml

# Supported file extensions
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv"}
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".m4a", ".flac", ".bwf"}


def find_media_files(folder: Path) -> tuple[list[Path], list[Path]]:
    """Scan a folder and separate files into video and audio lists."""
    videos = []
    audios = []

    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            videos.append(f)
        elif ext in AUDIO_EXTENSIONS:
            audios.append(f)

    return videos, audios


def print_progress(step: int, total: int, message: str):
    """Print progress to stderr."""
    pct = int(step / total * 100) if total > 0 else 0
    print(f"  [{pct:3d}%] {message}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        prog="fcpx-sync",
        description="Batch sync audio and video files for Final Cut Pro X.",
        epilog="Generates an FCPXML file with synchronized clips ready for import.",
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing video and audio files to sync.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output FCPXML file path. Defaults to <folder>/synced.fcpxml",
    )
    parser.add_argument(
        "--event-name",
        default="Synced Clips",
        help='Name for the FCPX event (default: "Synced Clips").',
    )
    parser.add_argument(
        "--video-folder",
        type=Path,
        default=None,
        help="Separate folder for video files (if not mixed in main folder).",
    )
    parser.add_argument(
        "--audio-folder",
        type=Path,
        default=None,
        help="Separate folder for audio files (if not mixed in main folder).",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )

    args = parser.parse_args()

    # Determine source folders
    main_folder = args.folder.resolve()
    if not main_folder.is_dir():
        print(f"Error: '{main_folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Collect files
    if args.video_folder or args.audio_folder:
        # Separate folders mode
        v_folder = (args.video_folder or main_folder).resolve()
        a_folder = (args.audio_folder or main_folder).resolve()
        videos, _ = find_media_files(v_folder)
        _, audios = find_media_files(a_folder)
    else:
        # Single folder mode
        videos, audios = find_media_files(main_folder)

    if not videos:
        print("Error: No video files found.", file=sys.stderr)
        sys.exit(1)
    if not audios:
        print("Error: No audio files found.", file=sys.stderr)
        sys.exit(1)

    # Print summary
    if not args.quiet:
        print(f"\n  FCPX Sync v0.1.0", file=sys.stderr)
        print(f"  {'─' * 40}", file=sys.stderr)
        print(f"  Found {len(videos)} video file(s):", file=sys.stderr)
        for v in videos:
            print(f"    • {v.name}", file=sys.stderr)
        print(f"  Found {len(audios)} audio file(s):", file=sys.stderr)
        for a in audios:
            print(f"    • {a.name}", file=sys.stderr)
        print(f"  {'─' * 40}", file=sys.stderr)
        print(f"  Analyzing waveforms...\n", file=sys.stderr)

    # Run sync matching
    callback = None if args.quiet else print_progress
    matches = match_files(videos, audios, progress_callback=callback)

    if not matches:
        print("\nError: No sync matches found.", file=sys.stderr)
        sys.exit(1)

    # Print results
    if not args.quiet:
        print(f"\n  {'─' * 40}", file=sys.stderr)
        print(f"  Matched {len(matches)} pair(s):\n", file=sys.stderr)
        for m in matches:
            direction = "audio leads" if m.offset_seconds < 0 else "audio trails"
            print(
                f"    {m.video_path.name}\n"
                f"      ↔ {m.audio_path.name}\n"
                f"      offset: {m.offset_seconds:+.3f}s ({direction})\n"
                f"      confidence: {m.correlation_score:.1%}\n",
                file=sys.stderr,
            )

    # Generate FCPXML
    xml_content = generate_fcpxml(matches, event_name=args.event_name)

    # Write output
    output_path = args.output or (main_folder / "synced.fcpxml")
    output_path.write_text(xml_content, encoding="utf-8")

    if not args.quiet:
        print(f"  {'─' * 40}", file=sys.stderr)
        print(f"  ✓ Wrote {output_path}", file=sys.stderr)
        print(f"\n  Open Final Cut Pro → File → Import → XML...", file=sys.stderr)
        print(f"  Select: {output_path}\n", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
