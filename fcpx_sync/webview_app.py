"""Pywebview-based GUI for Sync Hole.

Provides a native macOS/Windows/Linux window with an HTML/CSS/JS UI
and a Python backend API bridged via pywebview.
"""

import os
import shutil
import sys
import threading
from pathlib import Path

import webview

try:
    from .cli import run_sync
except ImportError:
    from fcpx_sync.cli import run_sync


def _fix_bundled_path():
    """Add PyInstaller bundle dir to PATH so ffprobe can be found."""
    if getattr(sys, "_MEIPASS", None):
        bundle_dir = sys._MEIPASS
        os.environ["PATH"] = bundle_dir + os.pathsep + os.environ.get("PATH", "")


_fix_bundled_path()


class Api:
    """Python API exposed to JavaScript via pywebview."""

    def __init__(self, window: webview.Window):
        self._window = window
        self._audio_folder: Path | None = None
        self._video_folder: Path | None = None
        self._output_path: Path | None = None
        self._mode: str = "timecode"
        self._sync_thread: threading.Thread | None = None

    # ── Folder selection ──────────────────────────────────────

    def select_folder(self, folder_type: str):
        """Open native folder dialog.  Returns the selected path string or None."""
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            allow_multiple=False,
        )
        if result and len(result) > 0:
            path = result[0]
            if folder_type == "audio":
                self._audio_folder = Path(path)
            elif folder_type == "video":
                self._video_folder = Path(path)
            return path
        return None

    # ── Mode toggle ───────────────────────────────────────────

    def set_mode(self, mode: str):
        """Set sync mode: 'timecode' or 'audio'."""
        self._mode = mode

    # ── Sync ──────────────────────────────────────────────────

    def start_sync(self):
        """Begin sync in a background thread.  Progress is pushed to JS."""
        if self._audio_folder is None or self._video_folder is None:
            self._eval("onSyncError('Select both folders first.')")
            return

        if self._sync_thread and self._sync_thread.is_alive():
            return  # already running

        self._sync_thread = threading.Thread(
            target=self._run_sync_thread,
            daemon=True,
        )
        self._sync_thread.start()

    def _run_sync_thread(self):
        """Worker thread — runs run_sync() and pushes results to JS."""

        def on_progress(message, step, total):
            safe = message.replace("\\", "\\\\").replace("'", "\\'")
            self._eval(f"onProgress('{safe}', {step}, {total})")

        try:
            output_path = run_sync(
                video_folder=self._video_folder,
                audio_folder=self._audio_folder,
                output_path=None,
                quiet=True,
                on_progress=on_progress,
                mode=self._mode,
            )
            self._output_path = output_path
            safe = str(output_path).replace("\\", "\\\\").replace("'", "\\'")
            self._eval(f"onSyncComplete('{safe}')")
        except Exception as e:
            safe = str(e).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
            self._eval(f"onSyncError('{safe}')")

    # ── Save ──────────────────────────────────────────────────

    def save_file(self):
        """Open native save dialog, copy the output file, return the saved path."""
        if self._output_path is None:
            return None

        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename="SyncedProject.fcpxml",
            file_types=("FCPXML Files (*.fcpxml)",),
        )
        if result:
            save_path = Path(result) if isinstance(result, str) else Path(result[0])
            if save_path != self._output_path:
                shutil.copy2(self._output_path, save_path)
            return str(save_path)
        return None

    # ── New batch reset ───────────────────────────────────────

    def new_batch(self):
        """Reset backend state for a new batch."""
        self._audio_folder = None
        self._video_folder = None
        self._output_path = None

    # ── Window controls ───────────────────────────────────────

    def close_window(self):
        self._window.destroy()

    def minimize_window(self):
        self._window.minimize()

    # ── Helpers ───────────────────────────────────────────────

    def _eval(self, js: str):
        """Thread-safe evaluate_js wrapper."""
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass  # window may be closed


def _get_html_path() -> str:
    """Resolve path to the HTML UI file."""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "ui", "index.html")
    return str(Path(__file__).parent / "ui" / "index.html")


def main():
    html_path = _get_html_path()

    window = webview.create_window(
        "Sync Hole",
        html_path,
        width=560,
        height=720,
        resizable=False,
        frameless=True,
        easy_drag=False,
    )

    api = Api(window)
    window.expose(api)

    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
