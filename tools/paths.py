"""Where things live. Override with environment variables:

  DUSK_DATA   the game's Dusk_Data folder
  DUSK_RANDO  a checkout of https://github.com/FlapjackRetro/dusk-rando (default: sibling of this repo)
"""
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(TOOLS)  # the repo root is the pack
DUSK_DATA = os.environ.get("DUSK_DATA", r"C:\Program Files (x86)\Steam\steamapps\common\Dusk\Dusk_Data")
DUSK_RANDO = os.environ.get("DUSK_RANDO", os.path.join(os.path.dirname(PACK), "dusk-rando"))
CACHE = os.path.join(TOOLS, "cache")
LOCATIONS_JSON = os.path.join(DUSK_RANDO, "apworld", "dusk", "data", "locations.json")
RAW_PICKUPS_JSON = os.path.join(DUSK_RANDO, "data", "raw_pickups.json")


def data_file(name):
    return os.path.join(DUSK_DATA, name)


def need(path, what):
    if not os.path.exists(path):
        sys.exit(f"{what} not found at {path} (see tools/README.md for DUSK_DATA / DUSK_RANDO)")
    return path
