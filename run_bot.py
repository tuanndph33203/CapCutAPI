#!/usr/bin/env python3
"""
Launcher for Telegram Remote Control Bot
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
    from capcut_api.bot.telegram_bot import main
    print("Khởi động Telegram Remote Control Bot...")
    main()
