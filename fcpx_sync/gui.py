"""Simple GUI for FCPX Sync using tkinter."""

import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from .cli import run_sync


class FCPXSyncApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FCPX Sync")
        self.root.resizable(False, False)

        # Size and center
        w, h = 480, 320
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Style
        bg = "#1e1e1e"
        fg = "#e0e0e0"
        accent = "#4a9eff"
        btn_bg = "#2d2d2d"
        entry_bg = "#2d2d2d"

        self.root.configure(bg=bg)

        # Title
        title = tk.Label(
            self.root, text="FCPX Sync", font=("Helvetica", 20, "bold"),
            bg=bg, fg=fg,
        )
        title.pack(pady=(20, 2))

        subtitle = tk.Label(
            self.root, text="Timecode-based batch sync for Final Cut Pro",
            font=("Helvetica", 11), bg=bg, fg="#888888",
        )
        subtitle.pack(pady=(0, 20))

        # Video folder
        vf = tk.Frame(self.root, bg=bg)
        vf.pack(fill="x", padx=30, pady=4)
        tk.Label(vf, text="Video Folder", font=("Helvetica", 11), bg=bg, fg=fg, width=12, anchor="w").pack(side="left")
        self.video_var = tk.StringVar()
        tk.Entry(vf, textvariable=self.video_var, bg=entry_bg, fg=fg, relief="flat",
                 insertbackground=fg, font=("Helvetica", 11)).pack(side="left", fill="x", expand=True, padx=(4, 4))
        tk.Button(vf, text="Browse", command=self._browse_video, bg=btn_bg, fg=fg,
                  relief="flat", font=("Helvetica", 10), cursor="hand2").pack(side="right")

        # Audio folder
        af = tk.Frame(self.root, bg=bg)
        af.pack(fill="x", padx=30, pady=4)
        tk.Label(af, text="Audio Folder", font=("Helvetica", 11), bg=bg, fg=fg, width=12, anchor="w").pack(side="left")
        self.audio_var = tk.StringVar()
        tk.Entry(af, textvariable=self.audio_var, bg=entry_bg, fg=fg, relief="flat",
                 insertbackground=fg, font=("Helvetica", 11)).pack(side="left", fill="x", expand=True, padx=(4, 4))
        tk.Button(af, text="Browse", command=self._browse_audio, bg=btn_bg, fg=fg,
                  relief="flat", font=("Helvetica", 10), cursor="hand2").pack(side="right")

        # Event name
        ef = tk.Frame(self.root, bg=bg)
        ef.pack(fill="x", padx=30, pady=4)
        tk.Label(ef, text="Event Name", font=("Helvetica", 11), bg=bg, fg=fg, width=12, anchor="w").pack(side="left")
        self.event_var = tk.StringVar(value="Synced Clips")
        tk.Entry(ef, textvariable=self.event_var, bg=entry_bg, fg=fg, relief="flat",
                 insertbackground=fg, font=("Helvetica", 11)).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Status label
        self.status_var = tk.StringVar(value="Select folders and click Sync")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var, font=("Helvetica", 10),
            bg=bg, fg="#888888",
        )
        self.status_label.pack(pady=(16, 4))

        # Sync button
        self.sync_btn = tk.Button(
            self.root, text="Sync", command=self._on_sync,
            bg=accent, fg="white", relief="flat", font=("Helvetica", 13, "bold"),
            cursor="hand2", width=20, height=1,
        )
        self.sync_btn.pack(pady=(4, 20))

    def _browse_video(self):
        folder = filedialog.askdirectory(title="Select Video Folder")
        if folder:
            self.video_var.set(folder)

    def _browse_audio(self):
        folder = filedialog.askdirectory(title="Select Audio Folder")
        if folder:
            self.audio_var.set(folder)

    def _on_sync(self):
        video_folder = self.video_var.get().strip()
        audio_folder = self.audio_var.get().strip()
        event_name = self.event_var.get().strip() or "Synced Clips"

        if not video_folder:
            messagebox.showwarning("Missing folder", "Please select a video folder.")
            return
        if not audio_folder:
            messagebox.showwarning("Missing folder", "Please select an audio folder.")
            return

        vp = Path(video_folder)
        ap = Path(audio_folder)

        if not vp.is_dir():
            messagebox.showerror("Error", f"Video folder not found:\n{video_folder}")
            return
        if not ap.is_dir():
            messagebox.showerror("Error", f"Audio folder not found:\n{audio_folder}")
            return

        self.sync_btn.configure(state="disabled", text="Syncing...")
        self.status_var.set("Reading timecodes and matching files...")
        self.root.update()

        # Run sync in a thread so the GUI doesn't freeze
        def _worker():
            try:
                output = run_sync(
                    video_folder=vp,
                    audio_folder=ap,
                    event_name=event_name,
                    quiet=True,
                )
                self.root.after(0, lambda: self._on_done(output))
            except Exception as e:
                self.root.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_done(self, output_path: Path):
        self.sync_btn.configure(state="normal", text="Sync")
        self.status_var.set(f"Done! Wrote {output_path.name}")
        messagebox.showinfo(
            "Sync Complete",
            f"FCPXML written to:\n{output_path}\n\n"
            f"Open Final Cut Pro → File → Import → XML\n"
            f"and select the file above.",
        )

    def _on_error(self, error_msg: str):
        self.sync_btn.configure(state="normal", text="Sync")
        self.status_var.set("Error — see details")
        messagebox.showerror("Sync Failed", error_msg)

    def run(self):
        self.root.mainloop()


def main():
    app = FCPXSyncApp()
    app.run()


if __name__ == "__main__":
    main()
