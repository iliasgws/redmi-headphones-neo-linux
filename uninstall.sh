#!/usr/bin/env bash
set -eu
python3 - <<'PY'
from pathlib import Path
import shutil
home=Path.home()
for path in (home/'.config/autostart/neo-popup.desktop', home/'.local/share/applications/neo-popup.desktop'):
    path.unlink(missing_ok=True)
folder=home/'.local/share/neo-popup'
if folder.is_symlink():
    folder.unlink()
elif folder.is_dir():
    shutil.rmtree(folder)
print('Removed the Neo popup user files and autostart entry.')
print('Stop any running Neo popup instance or log out to finish unloading it.')
PY
