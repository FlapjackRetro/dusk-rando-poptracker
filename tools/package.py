"""Zip the pack for release: dist/dusk_ap_tracker_v<version>.zip (everything except tools/ and repo files)."""
import json
import os
import zipfile

from paths import PACK

EXCLUDE_DIRS = {"tools", "dist", ".git", ".github", "__pycache__"}
EXCLUDE_FILES = {".gitignore", ".gitattributes"}

version = json.load(open(os.path.join(PACK, "manifest.json")))["package_version"]
os.makedirs(os.path.join(PACK, "dist"), exist_ok=True)
out = os.path.join(PACK, "dist", f"dusk_ap_tracker_v{version}.zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(PACK):
        rel = os.path.relpath(root, PACK)
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if rel == "." and f in EXCLUDE_FILES:
                continue
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, PACK))
print(out, os.path.getsize(out) // 1024, "KiB")
