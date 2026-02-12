"""Simple GUI for FCPX Sync using native macOS dialogs via osascript."""

import subprocess
import sys
from pathlib import Path

from .cli import run_sync


def _osascript(script: str) -> str:
    """Run an AppleScript and return the result."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def _choose_folder(prompt: str) -> str:
    """Show a native macOS folder picker dialog."""
    script = f'POSIX path of (choose folder with prompt "{prompt}")'
    result = _osascript(script)
    # Returns empty string if user cancelled
    return result.rstrip("/")


def _show_alert(title: str, message: str, icon: str = "note"):
    """Show a native macOS alert dialog. icon: note, caution, stop"""
    # Escape double quotes in the message
    msg = message.replace('"', '\\"').replace('\n', '\\n')
    script = (
        f'display alert "{title}" message "{msg}" '
        f'as {icon}'
    )
    _osascript(script)


def _show_error(title: str, message: str):
    _show_alert(title, message, icon="critical")


def main():
    print("\n  FCPX Sync — GUI Mode")
    print("  " + "─" * 40)

    # Step 1: Pick video folder
    print("\n  Select your VIDEO folder...")
    video_folder = _choose_folder("Select the folder containing your VIDEO files")
    if not video_folder:
        print("  Cancelled.")
        return

    video_path = Path(video_folder)
    print(f"  Video: {video_path}")

    # Step 2: Pick audio folder
    print("  Select your AUDIO folder...")
    audio_folder = _choose_folder("Select the folder containing your AUDIO files")
    if not audio_folder:
        print("  Cancelled.")
        return

    audio_path = Path(audio_folder)
    print(f"  Audio: {audio_path}")

    # Step 3: Run sync
    print("\n  Syncing...\n")
    try:
        output = run_sync(
            video_folder=video_path,
            audio_folder=audio_path,
            quiet=False,
        )
        _show_alert(
            "Sync Complete",
            f"FCPXML written to:\\n{output}\\n\\n"
            f"Open Final Cut Pro → File → Import → XML\\n"
            f"and select the file above.",
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        _show_error("Sync Failed", str(e))
        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
