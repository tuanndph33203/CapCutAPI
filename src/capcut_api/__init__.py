"""
CapCutAPI Package Architecture
Modular Layered Src Layout for CapCut Automation & Processing
"""
import sys
import os
from pathlib import Path

pkg_dir = Path(__file__).resolve().parent
subdirs = [
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

__version__ = "1.0.0"
