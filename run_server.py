#!/usr/bin/env python3
"""
Launcher for CapCut Draft API Server (Port 9001)
"""
import sys
import os
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add all module paths to sys.path
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
pkg_dir = src_dir / "capcut_api"
subdirs = [
    root_dir,
    src_dir,
    pkg_dir,
    pkg_dir / "api",
    pkg_dir / "automation",
    pkg_dir / "ai",
    pkg_dir / "processing",
    pkg_dir / "publisher",
    pkg_dir / "bot",
    pkg_dir / "core",
]
for d in subdirs:
    d_str = str(d)
    if d_str not in sys.path:
        sys.path.insert(0, d_str)

if __name__ == "__main__":
    from capcut_api.api.server_app import app, PORT
    print(f"Khởi động CapCut Draft REST API Server tại http://127.0.0.1:{PORT}")
    app.run(host="0.0.0.0", port=PORT)
