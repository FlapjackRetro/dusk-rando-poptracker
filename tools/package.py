"""Zip the pack for release and record it in versions.json (PopTracker's update feed).

    python tools/package.py

1. Builds dist/dusk_ap_tracker_v<version>.zip from the repo (everything except tools/, dist/, versions.json, ...).
2. Writes that zip's sha256 and release download URL into the matching entry of versions.json, creating the entry
   at the top if it's missing (fill in its changelog before releasing).

Then: commit versions.json, create GitHub release v<version>, and upload THIS zip unchanged. PopTracker refuses an
update whose sha256 doesn't match, so don't rebuild the zip after packaging.
"""
import hashlib
import json
import os
import sys
import zipfile

from paths import PACK

REPO = "FlapjackRetro/dusk-rando-poptracker"
EXCLUDE_DIRS = {"tools", "dist", ".git", ".github", "__pycache__"}
EXCLUDE_FILES = {".gitignore", ".gitattributes", "versions.json"}

version = json.load(open(os.path.join(PACK, "manifest.json")))["package_version"]
name = f"dusk_ap_tracker_v{version}.zip"
os.makedirs(os.path.join(PACK, "dist"), exist_ok=True)
out = os.path.join(PACK, "dist", name)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(PACK):
        rel = os.path.relpath(root, PACK)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for f in sorted(files):
            if rel == "." and f in EXCLUDE_FILES:
                continue
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, PACK))
sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
print(out, os.path.getsize(out) // 1024, "KiB")
print("sha256", sha)

vpath = os.path.join(PACK, "versions.json")
feed = json.load(open(vpath)) if os.path.exists(vpath) else {"versions": []}
entry = next((v for v in feed["versions"] if v["package_version"] == version), None)
if entry is None:
    entry = {"package_version": version, "changelog": []}
    feed["versions"].insert(0, entry)
entry["download_url"] = f"https://github.com/{REPO}/releases/download/v{version}/{name}"
entry["sha256"] = sha
for k in ("package_version", "download_url", "sha256", "changelog"):  # keep a stable key order
    entry[k] = entry.pop(k)
if feed["versions"][0] is not entry:
    sys.exit(f"versions.json: {version} must be the first (newest) entry")
with open(vpath, "w") as fh:
    json.dump(feed, fh, indent=2)
    fh.write("\n")
print("versions.json updated" + ("" if entry["changelog"] else " -- add a changelog for " + version))
