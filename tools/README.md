# Generator

Builds the pack from DUSK's Unity level files plus dusk-rando's `apworld/dusk/data/locations.json`.
Python 3.10+, `pip install -r tools/requirements.txt`. Reuses `tools/asset_extract/sf.py` from a dusk-rando
checkout for the SerializedFile reader.

## Setup

Two paths, set as environment variables (defaults in `paths.py`):

| Variable | Default | What |
|---|---|---|
| `DUSK_DATA` | `C:\Program Files (x86)\Steam\steamapps\common\Dusk\Dusk_Data` | the game's data folder |
| `DUSK_RANDO` | `../dusk-rando` next to this repo | a dusk-rando checkout |

## Running

```
python tools/build_pack.py              # everything (first run extracts level geometry into tools/cache/, ~2 min)
python tools/build_pack.py E1M3 E2M4    # re-render only these maps; the rest reuse tools/cache/coords/
python tools/compose.py E1M3            # preview one map in tools/preview/ (prints layers, size, connectors)
python tools/make_icons.py              # item icons (weapon/key glyphs come from DUSK's HUD textures)
python tools/package.py                 # release zip in dist/
```

Item IDs are read straight from the apworld's `items.py`; location IDs, names and positions from `locations.json`,
so a dusk-rando data change only needs a rebuild.

## How the maps are made

| File | What it does |
|---|---|
| `unitymesh.py` | Mesh / MeshFilter / MeshRenderer readers for Unity 2018.2. Handles static batching (renderers that point into `Combined Mesh (root: scene)`). |
| `textures.py` | Material → `_MainTex`, Texture2D decode (DXT1/DXT5 incl. alpha, RGB(A)24/32, RGB565, Alpha8), `.resS` streaming. |
| `scene.py` | Level file → world-space triangles with UVs/material, cached as `cache/level<N>.npz`. |
| `bands.py` | Per check: floor under it and lowest floor above it. Greedy minimum set of height layers so no check is hidden under a higher floor on its own layer; each cut is placed at the height with the least floor area so it doesn't slice through slopes. |
| `render.py` | Textured top-down rasteriser (per-triangle affine texture warps with mip selection); wall outlines from height steps. |
| `compose.py` | Finds each level's exits (EndLevelButton pickups + `EndLevelTriggerScript` loading zones, cached in `cache/exits.json`) and treats them like checks when building layers. Lays the layers out (highest on top, aligned on world X so connector lines run vertically), splits far-off clusters into detached panels, draws exit markers and the header. It can also draw red lines joining the same spot on two layers (stairs, ramps, drops); that is off by default and turned on per level with `"connectors": true`. Returns each check's pixel position. |
| `build_pack.py` | Writes `items/`, `locations/` (nearby checks share a pin), `maps/`, `layouts/` and the generated Lua tables. |
| `quick.py` | Level code ↔ Unity level-file index (`SCENE_IDX`) and a quick height-coloured debug render. |

## level_config.json — per-level overrides

```jsonc
{
  "E1M7": {
    "cuts": [-134.2, -126.7, -122.25],          // layer boundaries (world Y); omit for automatic
    "names": ["Crypts", "Graveyard", "Hill", "Church loft"],
    "force": {"E1M7 - Secret Area 2": 1},       // put a check on a specific layer (0 = lowest)
    "connectors": true,                         // draw red lines between layers on this map (off by default)
    "extra_connectors": [[0, 1, -110.5, 98.0]], // [lowerLayer, upperLayer, worldX, worldZ], e.g. a lift
    "exits": [[-5.0, -365.0, 79.2]],            // Level Complete pin position(s), world x/y/z; replaces the found exits
    "extra_exits": [[10.0, -50.0, 20.0]],       // ...or add to them
    "exit_label": "BOSS",                       // text drawn over the Level Complete pin (default EXIT)
    "max_connectors": 6, "margin": 14, "ppu": 6, "cluster_gap": 60
  }
}
```

(The file itself is plain JSON — no comments.) Automatic layers are the minimum that keeps every check visible, so a
check under one small overhang adds a whole layer; merge those by hand with `cuts` + `force` when the overhang
doesn't matter. World coordinates for a spot: `docs/LOCATIONS.csv` in dusk-rando has every check's x/y/z.

Known rough spots: levels with many layers wrap into two columns, and lines between columns run diagonally
(E1M9, E2M3); E2M1 and E2M8 have 8–9 automatic layers.
