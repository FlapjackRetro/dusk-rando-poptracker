"""AP item name -> id, read from dusk-rando's apworld (items.py) without needing Archipelago installed."""
import os
import sys
import types

from paths import DUSK_RANDO, TOOLS, need


def item_ids():
    sys.path.insert(0, os.path.join(TOOLS, "stub"))  # minimal BaseClasses stand-in
    pkg = types.ModuleType("dusk")
    pkg.__path__ = [need(os.path.join(DUSK_RANDO, "apworld", "dusk"), "dusk-rando apworld")]
    sys.modules.setdefault("dusk", pkg)
    from dusk import items
    return dict(items.ITEM_NAME_TO_ID)


if __name__ == "__main__":
    for k, v in item_ids().items():
        print(v, k)
