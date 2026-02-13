"""Command-line interface for FCPX Sync."""

import argparse
import sys
from pathlib import Path

from .sync_engine import probe_media, match_by_timecode, Timecode
from .fcpxml import generate_fcpxml

# Supported file extensions
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".r3d", ".braw"}
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".m4a", ".flac", ".bwf"}


def find_files(folder: Path, extensions: set) -> list:
    """Scan a folder for files with the given extensions.

    Skips macOS resource fork files (._*) and other hidden dot-files.
    """
    files = []
    for f in sorted(folder.iterdir()):
        if f.name.startswith("."):
            continue
        if f.is_file() and f.suffix.lower() in extensions:
            files.append(f)
    return files


def print_progress(step: int, total: int, message: str):
    """Print progress to stderr."""
    pct = int(step / total * 100) if total > 0 else 0
    print(f"  [{pct:3d}%] {message}", file=sys.stderr)


def run_sync(
    video_folder: Path,
    audio_folder: Path,
    output_path: Path = None,
    event_name: str = "Synced Clips",
    quiet: bool = False,
    on_progress=None,
    mode: str = "timecode",
) -> Path:
    """Core sync logic shared by CLI and GUI.

    Args:
        on_progress: Optional callback(message: str, step: int, total: int).
                     Called with human-readable progress updates.

    Returns the output file path.
    """
    def _emit(msg, step=0, total=0):
        if on_progress:
            on_progress(msg, step, total)

    videos = find_files(video_folder, VIDEO_EXTENSIONS)
    audios = find_files(audio_folder, AUDIO_EXTENSIONS)

    if not videos:
        raise FileNotFoundError(f"No video files found in {video_folder}")
    if not audios:
        raise FileNotFoundError(f"No audio files found in {audio_folder}")

    _emit(f"Found {len(videos)} video, {len(audios)} audio files", 0, 0)

    if not quiet:
        print(f"\n  FCPX Sync v0.1.0", file=sys.stderr)
        print(f"  {'─' * 40}", file=sys.stderr)
        print(f"  Found {len(videos)} video file(s):", file=sys.stderr)
        for v in videos:
            print(f"    • {v.name}", file=sys.stderr)
        print(f"  Found {len(audios)} audio file(s):", file=sys.stderr)
        for a in audios:
            print(f"    • {a.name}", file=sys.stderr)
        print(f"  {'─' * 40}", file=sys.stderr)
        print(f"  Reading timecodes...\n", file=sys.stderr)

    # Probe all files
    callback = None if quiet else print_progress
    total_files = len(videos) + len(audios)
    step = 0

    video_media = []
    for vp in videos:
        step += 1
        if callback:
            callback(step, total_files, f"Probing {vp.name}")
        _emit(f"Reading video: {vp.name}", step, total_files)
        try:
            media = probe_media(vp)
        except Exception as e:
            _emit(f"  Skipped {vp.name} ({e})", step, total_files)
            if not quiet:
                print(f"         SKIPPED ({e})", file=sys.stderr)
            continue
        tc_str = str(media.timecode) if media.timecode else "NONE"
        _emit(f"  TC: {tc_str}  dur: {media.duration:.1f}s", step, total_files)
        if not quiet:
            print(f"         TC: {tc_str}  dur: {media.duration:.1f}s", file=sys.stderr)
        video_media.append(media)

    audio_media = []
    for ap in audios:
        step += 1
        if callback:
            callback(step, total_files, f"Probing {ap.name}")
        _emit(f"Reading audio: {ap.name}", step, total_files)
        try:
            media = probe_media(ap)
        except Exception:
            _emit(f"  Skipped {ap.name} (ffprobe failed)", step, total_files)
            if not quiet:
                print(f"         SKIPPED (ffprobe failed)", file=sys.stderr)
            continue
        tc_str = str(media.timecode) if media.timecode else "NONE"
        _emit(f"  TC: {tc_str}  dur: {media.duration:.1f}s", step, total_files)
        if not quiet:
            print(f"         TC: {tc_str}  dur: {media.duration:.1f}s", file=sys.stderr)
        audio_media.append(media)

    # Match by selected mode
    if mode == "timecode":
        _emit("Matching by timecode...", total_files, total_files)
        if not quiet:
            print(f"\n  Matching by timecode...\n", file=sys.stderr)
        matches = match_by_timecode(video_media, audio_media, progress_callback=callback)
    elif mode == "audio":
        _emit("Matching by audio waveform...", total_files, total_files)
        if not quiet:
            print(f"\n  Matching by audio cross-correlation...\n", file=sys.stderr)
        try:
            from .audio_sync import match_by_audio
        except ImportError:
            raise RuntimeError(
                "Audio sync requires numpy. Install with: pip install sync-hole[audio]"
            )
        matches = match_by_audio(video_media, audio_media, progress_callback=callback)
        # Synthesise placeholder timecodes so generate_fcpxml() works unchanged.
        # Use 01:00:00:00 as the conventional base timecode for all clips.
        for m in matches:
            fps = m.video.fps_num / m.video.fps_den if m.video.fps_den else 24.0
            base_tc_seconds = 3600.0  # 01:00:00:00
            if m.video.timecode is None:
                m.video.timecode = Timecode.from_seconds(base_tc_seconds, fps=fps)
            if m.audio.timecode is None:
                audio_tc_seconds = base_tc_seconds - m.offset_seconds
                m.audio.timecode = Timecode.from_seconds(audio_tc_seconds, fps=fps)
    else:
        raise ValueError(f"Unknown sync mode: {mode!r}. Use 'timecode' or 'audio'.")

    if not matches:
        raise RuntimeError(f"No matches found using {mode} mode.")

    _emit(f"Matched {len(matches)} pair(s)", total_files, total_files)

    # Print results
    if not quiet:
        print(f"\n  {'─' * 40}", file=sys.stderr)
        print(f"  Matched {len(matches)} pair(s):\n", file=sys.stderr)
        for m in matches:
            print(
                f"    {m.video.path.name}  (TC {m.video.timecode})\n"
                f"      ↔ {m.audio.path.name}  (TC {m.audio.timecode})\n"
                f"      offset: {m.offset_seconds:+.3f}s\n",
                file=sys.stderr,
            )

    for m in matches:
        _emit(
            f"  {m.video.path.name} ↔ {m.audio.path.name}  "
            f"({m.offset_seconds:+.1f}s)",
            total_files, total_files,
        )

    # Generate FCPXML
    _emit("Generating FCPXML...", total_files, total_files)
    xml_content = generate_fcpxml(matches, event_name=event_name)

    # Write output
    if output_path is None:
        output_path = video_folder / "synced.fcpxml"
    output_path.write_text(xml_content, encoding="utf-8")

    _emit(f"Wrote {output_path.name}", total_files, total_files)

    if not quiet:
        print(f"  {'─' * 40}", file=sys.stderr)
        print(f"  ✓ Wrote {output_path}", file=sys.stderr)
        print(f"\n  Open Final Cut Pro → File → Import → XML...", file=sys.stderr)
        print(f"  Select: {output_path}\n", file=sys.stderr)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        prog="fcpx-sync",
        description="Batch sync audio and video files for Final Cut Pro X using timecode.",
        epilog="Generates an FCPXML file with synchronized clips ready for import.",
    )
    parser.add_argument(
        "video_folder",
        type=Path,
        help="Folder containing video files.",
    )
    parser.add_argument(
        "audio_folder",
        type=Path,
        help="Folder containing audio files.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output FCPXML file path. Defaults to <video_folder>/synced.fcpxml",
    )
    parser.add_argument(
        "--event-name",
        default="Synced Clips",
        help='Name for the FCPX event (default: "Synced Clips").',
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )
    parser.add_argument(
        "--mode",
        choices=["timecode", "audio"],
        default="timecode",
        help='Sync method: "timecode" (match by embedded TC) or "audio" (match by waveform).',
    )

    args = parser.parse_args()

    v_folder = args.video_folder.resolve()
    a_folder = args.audio_folder.resolve()

    if not v_folder.is_dir():
        print(f"Error: '{v_folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    if not a_folder.is_dir():
        print(f"Error: '{a_folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    try:
        run_sync(
            video_folder=v_folder,
            audio_folder=a_folder,
            output_path=args.output,
            event_name=args.event_name,
            quiet=args.quiet,
            mode=args.mode,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
