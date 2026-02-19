# gui.py
from __future__ import annotations

import contextlib
from logging import root
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tvd.core import (
    default_outname_from_url,
    ffmpeg_download,
    pick_best_candidate,
    sniff_media_urls,
    stream_download,
)


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path) 
            except Exception:
                icon_img = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, icon_img)

        self.title("Threads Video Downloader")
        self.geometry("820x520")
        self.minsize(760, 480)

        self.url_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.headful_var = tk.BooleanVar(value=False)
        self.timeout_var = tk.IntVar(value=35)
        self.user_data_dir_var = tk.StringVar()

        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build()

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        for c in range(5):
            root.columnconfigure(c, weight=1)

        r = 0

        ttk.Label(root, text="Threads URL").grid(row=r, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.url_var).grid(row=r, column=1, columnspan=3, sticky="ew", padx=(8, 0))
        ttk.Button(root, text="Paste", command=self._paste).grid(row=r, column=4, sticky="ew", padx=(8, 0))
        r += 1

        ttk.Label(root, text="Output file").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(root, textvariable=self.out_var).grid(row=r, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(6, 0))
        ttk.Button(root, text="Browse…", command=self._browse_out).grid(row=r, column=4, sticky="ew", padx=(8, 0), pady=(6, 0))
        r += 1

        ttk.Label(root, text="User data dir (optional)").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(root, textvariable=self.user_data_dir_var).grid(row=r, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(6, 0))
        ttk.Button(root, text="Browse…", command=self._browse_profile).grid(row=r, column=4, sticky="ew", padx=(8, 0), pady=(6, 0))
        r += 1

        opts = ttk.LabelFrame(root, text="Options", padding=10)
        opts.grid(row=r, column=0, columnspan=5, sticky="ew", pady=(10, 0))
        opts.columnconfigure(3, weight=1)

        ttk.Checkbutton(opts, text="Headful browser (show Chromium window)", variable=self.headful_var).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

        ttk.Label(opts, text="Timeout (seconds)").grid(row=0, column=2, sticky="e", padx=(12, 6))
        ttk.Spinbox(opts, from_=5, to=600, textvariable=self.timeout_var, width=8).grid(row=0, column=3, sticky="w")

        ttk.Button(opts, text="Auto name from URL", command=self._auto_name).grid(row=0, column=4, sticky="e", padx=(12, 0))

        r += 1

        ttk.Separator(root).grid(row=r, column=0, columnspan=5, sticky="ew", pady=12)
        r += 1

        self.pb = ttk.Progressbar(root, variable=self.progress_var, maximum=100.0)
        self.pb.grid(row=r, column=0, columnspan=5, sticky="ew")
        r += 1

        ttk.Label(root, textvariable=self.status_var).grid(row=r, column=0, columnspan=5, sticky="w", pady=(6, 0))
        r += 1

        self.log = tk.Text(root, height=12, wrap="word")
        self.log.grid(row=r, column=0, columnspan=5, sticky="nsew", pady=(8, 0))
        root.rowconfigure(r, weight=1)
        r += 1

        btns = ttk.Frame(root)
        btns.grid(row=r, column=0, columnspan=5, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Download", command=self._start_download).pack(side="left")
        ttk.Button(btns, text="Find candidates (dump)", command=self._start_dump).pack(side="left", padx=8)
        ttk.Button(btns, text="Clear log", command=lambda: self.log.delete("1.0", "end")).pack(side="right")

        # Credits
        credits = ttk.Label(
            root,
            text="Threads Video Downloader • Built by Podjisin • Powered by Playwright & ffmpeg",
            anchor="center",
            foreground="#666666",
        )
        credits.grid(row=r + 1, column=0, columnspan=5, sticky="ew", pady=(10, 0))

    def _paste(self):
        with contextlib.suppress(Exception):
            self.url_var.set(self.clipboard_get().strip())

    def _browse_out(self):
        if path := filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        ):
            self.out_var.set(path)

    def _browse_profile(self):
        if path := filedialog.askdirectory():
            self.user_data_dir_var.set(path)

    def _auto_name(self):
        url = self.url_var.get().strip()
        if not url:
            return
        base = default_outname_from_url(url)
        self.out_var.set(os.path.abspath(f"{base}.mp4"))

    def _ui_log(self, msg: str):
        self.after(0, lambda: (self.log.insert("end", msg + "\n"), self.log.see("end")))

    def _ui_status(self, msg: str):
        self.after(0, lambda: self.status_var.set(msg))

    def _ui_progress(self, done: int, total: int | None, state: str):
        def upd():
            if total and total > 0:
                self.progress_var.set((done / total) * 100.0)
                self.status_var.set(f"{state} — {done}/{total} bytes")
            else:
                self.progress_var.set((done % (50 * 1024 * 1024)) / (50 * 1024 * 1024) * 100.0)
                self.status_var.set(f"{state} — {done} bytes")
        self.after(0, upd)

    def _start_dump(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Paste a Threads URL first.")
            return

        def worker():
            try:
                self.progress_var.set(0.0)
                self._ui_status("Sniffing media URLs...")
                cands, ua = sniff_media_urls(
                    url,
                    playwright_timeout_s=int(self.timeout_var.get()),
                    headful=bool(self.headful_var.get()),
                    user_data_dir=self.user_data_dir_var.get().strip() or None,
                    on_log=self._ui_log,
                )
                self._ui_log(f"User-Agent: {ua}")
                if not cands:
                    self._ui_log("No candidates found.")
                    self._ui_status("No candidates found.")
                    return

                self._ui_log("Candidates:")
                for i, c in enumerate(cands):
                    self._ui_log(f"  [{i}] {c.type} len={c.content_length} status={c.status}")
                    self._ui_log(f"      {c.url}")

                self._ui_status(f"Found {len(cands)} candidates.")
            except Exception as e:
                self._ui_log(f"ERROR: {e}")
                self._ui_status("Error")
                messagebox.showerror("Error", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Paste a Threads URL first.")
            return

        out = self.out_var.get().strip()
        if not out:
            base = default_outname_from_url(url)
            out = os.path.abspath(f"{base}.mp4")
            self.out_var.set(out)

        def worker():
            try:
                self.progress_var.set(0.0)
                self._ui_status("Sniffing media URLs...")
                self._ui_log(f"URL: {url}")

                cands, ua = sniff_media_urls(
                    url,
                    playwright_timeout_s=int(self.timeout_var.get()),
                    headful=bool(self.headful_var.get()),
                    user_data_dir=self.user_data_dir_var.get().strip() or None,
                    on_log=self._ui_log,
                )

                if not cands:
                    self._ui_status("No media found.")
                    self._ui_log("No media URLs found.")
                    return

                best = pick_best_candidate(cands)
                if not best:
                    self._ui_status("No suitable candidate.")
                    self._ui_log("Could not pick a candidate.")
                    return

                self._ui_log(f"Picked: {best.type} len={best.content_length} status={best.status}")
                headers = {"User-Agent": ua, "Referer": url}

                if best.type == "mp4":
                    self._ui_status("Downloading MP4...")
                    stream_download(
                        best.url,
                        out,
                        headers=headers,
                        on_progress=lambda d, t, s: self._ui_progress(d, t, s),
                    )
                else:
                    self._ui_status("Downloading via ffmpeg...")
                    ffmpeg_download(
                        best.url,
                        out,
                        referer=url,
                        user_agent=ua,
                        on_log=self._ui_log,
                    )
                    self._ui_progress(100, 100, "Done")

                self._ui_log(f"Saved: {out}")
                self._ui_status("Done")
                messagebox.showinfo("Done", f"Saved:\n{out}")

            except Exception as e:
                self._ui_log(f"ERROR: {e}")
                self._ui_status("Error")
                messagebox.showerror("Error", str(e))

        threading.Thread(target=worker, daemon=True).start()


def run():
    App().mainloop()


if __name__ == "__main__":
    run()
