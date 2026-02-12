"""Native Mac GUI application for FCPX Sync."""

import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from .cli import run_sync


# Colors
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
ACCENT_HOVER = "#74c7ec"
BTN_BG = "#313244"
BTN_ACTIVE = "#45475a"
ENTRY_BG = "#181825"
SUCCESS = "#a6e3a1"
ERROR = "#f38ba8"
MUTED = "#6c7086"


class FolderRow(tk.Frame):
    """A row with a label, path display, and browse button."""

    def __init__(self, parent, label_text, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self.path_var = tk.StringVar(value="No folder selected")

        label = tk.Label(
            self, text=label_text, font=("SF Pro Display", 13, "bold"),
            fg=ACCENT, bg=BG, anchor="w",
        )
        label.pack(fill="x", padx=4, pady=(8, 2))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=4)

        path_label = tk.Label(
            row, textvariable=self.path_var, font=("SF Mono", 11),
            fg=MUTED, bg=ENTRY_BG, anchor="w", padx=10, pady=8,
            relief="flat",
        )
        path_label.pack(side="left", fill="x", expand=True, ipady=2)

        browse_btn = tk.Button(
            row, text="Browse", font=("SF Pro Display", 12),
            fg=FG, bg=BTN_BG, activeforeground=FG, activebackground=BTN_ACTIVE,
            relief="flat", padx=16, pady=6, cursor="hand2",
            command=self._browse,
        )
        browse_btn.pack(side="right", padx=(8, 0))

    def _browse(self):
        folder = filedialog.askdirectory(title=f"Select folder")
        if folder:
            self.path_var.set(folder)

    def get_path(self):
        val = self.path_var.get()
        if val == "No folder selected":
            return None
        return Path(val)


class SaveRow(tk.Frame):
    """A row for choosing the output file save location."""

    def __init__(self, parent, label_text, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self.path_var = tk.StringVar(value="Same as video folder")

        label = tk.Label(
            self, text=label_text, font=("SF Pro Display", 13, "bold"),
            fg=ACCENT, bg=BG, anchor="w",
        )
        label.pack(fill="x", padx=4, pady=(8, 2))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=4)

        path_label = tk.Label(
            row, textvariable=self.path_var, font=("SF Mono", 11),
            fg=MUTED, bg=ENTRY_BG, anchor="w", padx=10, pady=8,
            relief="flat",
        )
        path_label.pack(side="left", fill="x", expand=True, ipady=2)

        browse_btn = tk.Button(
            row, text="Browse", font=("SF Pro Display", 12),
            fg=FG, bg=BTN_BG, activeforeground=FG, activebackground=BTN_ACTIVE,
            relief="flat", padx=16, pady=6, cursor="hand2",
            command=self._browse,
        )
        browse_btn.pack(side="right", padx=(8, 0))

    def _browse(self):
        path = filedialog.asksaveasfilename(
            title="Save FCPXML as",
            defaultextension=".fcpxml",
            filetypes=[("FCPXML files", "*.fcpxml"), ("All files", "*.*")],
            initialfile="synced.fcpxml",
        )
        if path:
            self.path_var.set(path)

    def get_path(self):
        val = self.path_var.get()
        if val == "Same as video folder":
            return None
        return Path(val)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FCPX Sync")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # Window size
        w, h = 580, 420
        self.root.geometry(f"{w}x{h}")

        # Try to center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        # Title
        title = tk.Label(
            self.root, text="FCPX Sync", font=("SF Pro Display", 22, "bold"),
            fg=FG, bg=BG,
        )
        title.pack(pady=(20, 0))

        subtitle = tk.Label(
            self.root, text="Batch sync video + audio by timecode",
            font=("SF Pro Display", 12), fg=MUTED, bg=BG,
        )
        subtitle.pack(pady=(2, 12))

        # Folder rows
        content = tk.Frame(self.root, bg=BG)
        content.pack(fill="x", padx=24)

        self.video_row = FolderRow(content, "Video Folder")
        self.video_row.pack(fill="x")

        self.audio_row = FolderRow(content, "Audio Folder")
        self.audio_row.pack(fill="x")

        self.save_row = SaveRow(content, "Save Location")
        self.save_row.pack(fill="x")

        # Sync button
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(pady=(20, 0))

        self.sync_btn = tk.Button(
            btn_frame, text="Sync", font=("SF Pro Display", 15, "bold"),
            fg=BG, bg=ACCENT, activeforeground=BG, activebackground=ACCENT_HOVER,
            relief="flat", padx=48, pady=10, cursor="hand2",
            command=self._on_sync,
        )
        self.sync_btn.pack()

        # Status
        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var, font=("SF Pro Display", 11),
            fg=MUTED, bg=BG, wraplength=500,
        )
        self.status_label.pack(pady=(12, 0))

    def _set_status(self, text, color=MUTED):
        self.status_var.set(text)
        self.status_label.configure(fg=color)
        self.root.update_idletasks()

    def _on_sync(self):
        video_path = self.video_row.get_path()
        audio_path = self.audio_row.get_path()
        output_path = self.save_row.get_path()

        if not video_path:
            self._set_status("Please select a video folder.", ERROR)
            return
        if not audio_path:
            self._set_status("Please select an audio folder.", ERROR)
            return
        if not video_path.is_dir():
            self._set_status(f"Video folder not found: {video_path}", ERROR)
            return
        if not audio_path.is_dir():
            self._set_status(f"Audio folder not found: {audio_path}", ERROR)
            return

        self.sync_btn.configure(state="disabled", text="Syncing...", bg=MUTED)
        self._set_status("Reading timecodes and matching files...", FG)

        # Run sync in background thread to keep UI responsive
        thread = threading.Thread(
            target=self._run_sync_thread,
            args=(video_path, audio_path, output_path),
            daemon=True,
        )
        thread.start()

    def _run_sync_thread(self, video_path, audio_path, output_path):
        try:
            result = run_sync(
                video_folder=video_path,
                audio_folder=audio_path,
                output_path=output_path,
                quiet=True,
            )
            self.root.after(0, self._on_success, result)
        except Exception as e:
            self.root.after(0, self._on_error, str(e))

    def _on_success(self, output_path):
        self.sync_btn.configure(state="normal", text="Sync", bg=ACCENT)
        self._set_status(f"Done! Saved to: {output_path}", SUCCESS)
        messagebox.showinfo(
            "Sync Complete",
            f"FCPXML written to:\n{output_path}\n\n"
            f"Open Final Cut Pro \u2192 File \u2192 Import \u2192 XML\n"
            f"and select the file above.",
        )

    def _on_error(self, error_msg):
        self.sync_btn.configure(state="normal", text="Sync", bg=ACCENT)
        self._set_status(f"Error: {error_msg}", ERROR)

    def run(self):
        self.root.mainloop()


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
