"""Native Mac GUI application for FCPX Sync."""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont
from pathlib import Path

try:
    from .cli import run_sync
except ImportError:
    from fcpx_sync.cli import run_sync


def _fix_bundled_path():
    """Add PyInstaller bundle dir to PATH so ffprobe can be found."""
    if getattr(sys, '_MEIPASS', None):
        bundle_dir = sys._MEIPASS
        os.environ['PATH'] = bundle_dir + os.pathsep + os.environ.get('PATH', '')


_fix_bundled_path()


# ── Color Palette ───────────────────────────────────────────
# Deep dark base with cool-toned accents (inspired by pro NLE UIs)
BG = "#13131a"
SURFACE = "#1c1c27"
RAISED = "#353548"
BORDER = "#2e2e42"
FG = "#e2e4f0"
DIM = "#8b8da6"
ACCENT = "#6ea5f7"
ACCENT_DIM = "#4a7fd4"
TEAL = "#5cd4c0"
RED = "#f06b8a"
GREEN = "#6ee7a0"
LOG_BG = "#0e0e14"
BTN_FG = "#ffffff"


# ── Helpers ─────────────────────────────────────────────────

class PickerRow(tk.Frame):
    """A file/folder picker row: section label, path display, browse button."""

    # Max characters shown in the path label before truncating with "..."
    MAX_PATH_CHARS = 38

    def __init__(self, parent, label_text, placeholder, browse_fn, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._placeholder = placeholder
        self._full_path = None
        self._browse_fn = browse_fn
        self._display_var = tk.StringVar(value=placeholder)

        # Section label
        lbl = tk.Label(
            self, text=label_text, font=("Helvetica Neue", 11),
            fg=ACCENT, bg=BG, anchor="w",
        )
        lbl.pack(fill="x", pady=(0, 4))

        # Row container with border
        row = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        row.pack(fill="x")

        inner = tk.Frame(row, bg=SURFACE)
        inner.pack(fill="both")

        # Browse button — pack FIRST so it always reserves its space
        btn = tk.Button(
            inner, text="BROWSE", width=8,
            font=("Helvetica Neue", 11, "bold"),
            fg=BG, bg=ACCENT_DIM, activeforeground=BG, activebackground=ACCENT,
            relief="flat", padx=14, pady=6, bd=0, highlightthickness=0,
            command=self._on_browse,
        )
        btn.pack(side="right", padx=6, pady=4)

        # Path display — takes remaining space, text truncated with "..."
        self._path_lbl = tk.Label(
            inner, textvariable=self._display_var,
            font=("Menlo", 11), fg=DIM, bg=SURFACE,
            anchor="w", padx=12, pady=10,
        )
        self._path_lbl.pack(side="left", fill="x", expand=True)

    @staticmethod
    def _truncate(path_str, max_chars):
        """Shorten a path to max_chars, preserving the tail with '...'."""
        if len(path_str) <= max_chars:
            return path_str
        return "\u2026" + path_str[-(max_chars - 1):]

    def _on_browse(self):
        result = self._browse_fn()
        if result:
            self._full_path = result
            self._display_var.set(self._truncate(result, self.MAX_PATH_CHARS))
            self._path_lbl.configure(fg=FG)

    def get_path(self):
        if self._full_path is None:
            return None
        return Path(self._full_path)


def _browse_folder():
    return filedialog.askdirectory(title="Select folder")


def _browse_save():
    return filedialog.asksaveasfilename(
        title="Save FCPXML as",
        defaultextension=".fcpxml",
        filetypes=[("FCPXML files", "*.fcpxml"), ("All files", "*.*")],
        initialfile="synced.fcpxml",
    )


# ── Main Application ───────────────────────────────────────

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FCPX Sync")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        w, h = 560, 560
        self.root.geometry(f"{w}x{h}")
        self.root.update_idletasks()
        sx = (self.root.winfo_screenwidth() // 2) - (w // 2)
        sy = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{sx}+{sy}")

        self._build()

    # ── Layout ──────────────────────────────────────────────

    def _build(self):
        # Title bar area
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 0))

        tk.Label(
            header, text="FCPX SYNC",
            font=("Helvetica Neue", 20, "bold"), fg=FG, bg=BG,
        ).pack(side="left")

        tk.Label(
            header, text="V0.2",
            font=("Helvetica Neue", 11), fg=DIM, bg=BG,
        ).pack(side="left", padx=(8, 0), pady=(6, 0))

        # Subtitle
        tk.Label(
            self.root,
            text="BATCH SYNC VIDEO + AUDIO BY TIMECODE",
            font=("Helvetica Neue", 11), fg=DIM, bg=BG, anchor="w",
        ).pack(fill="x", padx=28, pady=(2, 16))

        # ── Picker rows ────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="x", padx=28)

        self.video_row = PickerRow(
            body, "VIDEO FOLDER", "NO FOLDER SELECTED", _browse_folder,
        )
        self.video_row.pack(fill="x", pady=(0, 10))

        self.audio_row = PickerRow(
            body, "AUDIO FOLDER", "NO FOLDER SELECTED", _browse_folder,
        )
        self.audio_row.pack(fill="x", pady=(0, 10))

        self.save_row = PickerRow(
            body, "SAVE LOCATION", "SAME AS VIDEO FOLDER", _browse_save,
        )
        self.save_row.pack(fill="x", pady=(0, 16))

        # ── Sync button ────────────────────────────────────
        self.sync_btn = tk.Button(
            body, text="SYNC",
            font=("Helvetica Neue", 14, "bold"),
            fg=BG, bg=ACCENT, activeforeground=BG, activebackground=ACCENT_DIM,
            relief="flat", pady=10, bd=0, highlightthickness=0,
            command=self._on_sync,
        )
        self.sync_btn.pack(fill="x", ipady=2)

        # ── Progress log ───────────────────────────────────
        log_lbl = tk.Label(
            body, text="LOG", font=("Helvetica Neue", 10),
            fg=DIM, bg=BG, anchor="w",
        )
        log_lbl.pack(fill="x", pady=(14, 3))

        log_border = tk.Frame(body, bg=BORDER, padx=1, pady=1)
        log_border.pack(fill="x")

        self.log_text = tk.Text(
            log_border, height=7,
            font=("Menlo", 10), fg=DIM, bg=LOG_BG,
            relief="flat", padx=10, pady=8, bd=0,
            highlightthickness=0, wrap="word",
            insertbackground=LOG_BG, selectbackground=BORDER,
            state="disabled",
        )
        self.log_text.pack(fill="both")

        # Configure tag colors for log
        self.log_text.tag_configure("info", foreground=DIM)
        self.log_text.tag_configure("file", foreground=ACCENT)
        self.log_text.tag_configure("match", foreground=TEAL)
        self.log_text.tag_configure("done", foreground=GREEN)
        self.log_text.tag_configure("err", foreground=RED)

    # ── Log helpers ─────────────────────────────────────────

    def _log(self, text, tag="info"):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()

    def _log_clear(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ── Progress callback (called from worker thread) ──────

    def _on_progress(self, message, step, total):
        """Thread-safe progress handler — schedules log update on main thread."""
        # Determine tag from message content
        tag = "info"
        if message.startswith("Reading video:") or message.startswith("Reading audio:"):
            tag = "file"
        elif "TC:" in message:
            tag = "info"
        elif "Matched" in message or "\u2194" in message:
            tag = "match"
        elif "Wrote" in message or "Generating" in message:
            tag = "done"
        elif "Skipped" in message:
            tag = "err"

        self.root.after(0, self._log, message, tag)

        # Update button text with progress percentage
        if total > 0:
            pct = int(step / total * 100)
            self.root.after(0, lambda: self.sync_btn.configure(
                text=f"SYNCING... {pct}%"
            ))

    # ── Sync logic ──────────────────────────────────────────

    def _on_sync(self):
        video_path = self.video_row.get_path()
        audio_path = self.audio_row.get_path()
        output_path = self.save_row.get_path()

        if not video_path:
            self._log("PLEASE SELECT A VIDEO FOLDER.", "err")
            return
        if not audio_path:
            self._log("PLEASE SELECT AN AUDIO FOLDER.", "err")
            return
        if not video_path.is_dir():
            self._log(f"VIDEO FOLDER NOT FOUND: {video_path}", "err")
            return
        if not audio_path.is_dir():
            self._log(f"AUDIO FOLDER NOT FOUND: {audio_path}", "err")
            return

        self._log_clear()
        self.sync_btn.configure(state="disabled", text="SYNCING...", bg=DIM)
        self._log("STARTING SYNC...", "info")

        thread = threading.Thread(
            target=self._run_sync,
            args=(video_path, audio_path, output_path),
            daemon=True,
        )
        thread.start()

    def _run_sync(self, video_path, audio_path, output_path):
        try:
            result = run_sync(
                video_folder=video_path,
                audio_folder=audio_path,
                output_path=output_path,
                quiet=True,
                on_progress=self._on_progress,
            )
            self.root.after(0, self._on_done, result)
        except Exception as e:
            self.root.after(0, self._on_fail, str(e))

    def _on_done(self, output_path):
        self.sync_btn.configure(state="normal", text="SYNC", bg=ACCENT)
        self._log(f"\nDONE \u2192 {output_path}", "done")
        messagebox.showinfo(
            "Sync Complete",
            f"FCPXML written to:\n{output_path}\n\n"
            f"Open Final Cut Pro \u2192 File \u2192 Import \u2192 XML\n"
            f"and select the file above.",
        )

    def _on_fail(self, error_msg):
        self.sync_btn.configure(state="normal", text="SYNC", bg=ACCENT)
        self._log(f"\nError: {error_msg}", "err")

    def run(self):
        self.root.mainloop()


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
