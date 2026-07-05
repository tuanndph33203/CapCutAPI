import sys
import os
from pathlib import Path

# Add current dir to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from capcut_gui_app import load_global_settings, save_global_settings

settings = load_global_settings()
# Trigger save which handles extraction to .env and replacement with env: references
save_global_settings(settings)
print("Successfully extracted raw keys to .env and cleaned global_pipeline_settings.json!")
