from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
import tkinter as tk


BASE_URL = "http://127.0.0.1:5000"


def request(path: str, payload: dict | None = None) -> str:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace")
        return "OK"
    except urllib.error.URLError as exc:
        return f"ERR {exc}"


def post(path: str, payload: dict | None = None) -> str:
    return request(path, payload or {})


def stop_pipeline() -> str:
    post("/api/pause", {})
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process CapCut -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return "STOP"


class Overlay(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pipeline")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(bg="#101018")
        self.geometry("+20+80")

        self.status = tk.StringVar(value="Ready")
        self.make_button("Start", lambda: self.call("/api/start", {"restart_all": True, "start_from_step_1": True}))
        self.make_button("Pause", lambda: self.call("/api/pause", {}))
        self.make_button("Resume", lambda: self.call("/api/resume", {}))
        self.make_button("Stop", self.stop)
        tk.Label(self, textvariable=self.status, bg="#101018", fg="#d6d6e7", font=("Segoe UI", 8), width=22).pack(padx=6, pady=(2, 6))

    def make_button(self, text: str, command) -> None:
        tk.Button(
            self,
            text=text,
            command=command,
            width=10,
            bg="#24243a",
            fg="#ffffff",
            activebackground="#00c8d7",
            activeforeground="#050508",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        ).pack(padx=6, pady=3)

    def call(self, path: str, payload: dict) -> None:
        self.status.set(post(path, payload))

    def stop(self) -> None:
        self.status.set(stop_pipeline())


if __name__ == "__main__":
    Overlay().mainloop()
