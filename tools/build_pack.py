"""Build the DUSK Archipelago PopTracker pack from dusk-rando's locations.json + the rendered level maps."""
import json
import os
import shutil
import sys
from collections import defaultdict

from PIL import Image

from compose import compose

from paths import CACHE, LOCATIONS_JSON, PACK, TOOLS, need
from item_ids import item_ids

ROOT = TOOLS
DATA = json.load(open(need(LOCATIONS_JSON, "dusk-rando locations.json")))
ITEM_IDS = item_ids()
VERSION = "0.2.0"
REPO = "FlapjackRetro/dusk-rando-poptracker"
VERSIONS_URL = f"https://raw.githubusercontent.com/{REPO}/main/versions.json"

LEVELS = DATA["levels"]
LOCS = [l for l in DATA["locations"] if l["vanilla_item"] != "Thermal Suit"]  # never a check (VANILLA_ONLY_ITEMS)
EPISODE_NAMES = {1: "Episode 1: The Foothills", 2: "Episode 2: The Facilities", 3: "Episode 3: The Nameless City"}
CAT_OPT = {"weapons": "opt_weapons", "keys": "opt_keys", "powerups": "opt_powerups", "secrets": "opt_secrets",
           "treasure_chests": "opt_treasure_chests", "health": "opt_health", "armor": "opt_armor", "ammo": "opt_ammo"}
WEAPON_CODES = {"Progressive Pistol": "pistol", "Progressive Shotgun": "shotgun", "Super Shotgun": "super_shotgun",
                "Assault Rifle": "assault_rifle", "Hunting Rifle": "hunting_rifle", "Crossbow": "crossbow",
                "Mortar": "mortar", "Riveter": "riveter", "Sword": "sword"}
CLUSTER_PX = 15


def lc(code):
    return code.lower()


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def short(name, code):
    return name[len(code) + 3:] if name.startswith(code + " - ") else name


def build_maps(only=None):
    coords, metas = {}, {}
    os.makedirs(f"{PACK}/images/maps", exist_ok=True)
    for lv in LEVELS:
        code = lv["code"]
        out = f"{PACK}/images/maps/{code}.png"
        if only and code not in only and os.path.exists(f"{CACHE}/coords/{code}.json"):
            c = json.load(open(f"{CACHE}/coords/{code}.json"))
            coords[code], metas[code] = c["coords"], c["meta"]
            continue
        c, m = compose(code, out)
        # 256-colour palette keeps the pack small; the maps are flat-shaded so it is visually lossless enough
        Image.open(out).convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
            out, optimize=True)
        coords[code], metas[code] = c, m
        os.makedirs(f"{CACHE}/coords", exist_ok=True)
        json.dump({"coords": c, "meta": m}, open(f"{CACHE}/coords/{code}.json", "w"))
        print(code, m["size"], m["per_layer"], file=sys.stderr)
    return coords, metas


def cluster(points):
    """points: list of (name, x, y, layer) -> list of groups (lists of names). Union-find on pixel distance."""
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            a, b = points[i], points[j]
            if a[3] == b[3] and abs(a[1] - b[1]) <= CLUSTER_PX and abs(a[2] - b[2]) <= CLUSTER_PX:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i, p in enumerate(points):
        groups[find(i)].append(p)
    return list(groups.values())


def build_locations(coords):
    by_ep = defaultdict(list)
    loc_map = {}
    for lv in LEVELS:
        code = lv["code"]
        parent_name = f"{code} {lv['name']}".replace("/", "-").replace(",", "")
        locs = [l for l in LOCS if l["level"] == code and l["category"] != "level_complete"]
        pts = [(l, *coords[code][l["name"]]) for l in locs]
        groups = cluster(pts)
        groups.sort(key=lambda g: (g[0][2], g[0][1]))
        children = []
        used = set()
        for g in groups:
            g.sort(key=lambda p: p[0]["id"])
            first = short(g[0][0]["name"], code)
            name = first if len(g) == 1 else f"{first} (+{len(g) - 1})"
            n = 2
            base = name
            while name in used:
                name = f"{base} #{n}"; n += 1
            used.add(name)
            sections = []
            for l, x, y, layer in g:
                sec = {"name": short(l["name"], code), "access_rules": [f"$check|{l['id']}"]}
                if l["category"] in CAT_OPT:
                    sec["visibility_rules"] = [CAT_OPT[l["category"]]]
                sections.append(sec)
                loc_map[l["id"]] = f"@{parent_name}/{name}/{sec['name']}"
            x = round(sum(p[1] for p in g) / len(g))
            y = round(sum(p[2] for p in g) / len(g))
            cats = {p[0]["category"] for p in g}
            children.append({"name": name, "sections": sections, "map_locations": [{"map": code, "x": x, "y": y}]})
        # Level Complete: its own pin on every exit (button / loading zone) of the level
        lcl = next(l for l in LOCS if l["level"] == code and l["category"] == "level_complete")
        sec = {"name": "Level Complete", "access_rules": [f"$check|{lcl['id']}"]}
        loc_map[lcl["id"]] = f"@{parent_name}/Level Complete/Level Complete"
        children.append({"name": "Level Complete", "sections": [sec], "map_locations": [
            {"map": code, "x": x, "y": y, "size": 44} for x, y, _ in coords[code][lcl["name"]]]})
        by_ep[lv["episode"]].append({
            "name": parent_name,
            "access_rules": [f"$can_enter|{code}"],
            "visibility_rules": [f"inc_{lc(code)}"],
            "children": children,
        })
    for ep, lst in by_ep.items():
        wjson(f"{PACK}/locations/episode{ep}.json", lst)
    return loc_map


def build_items():
    items = []
    for lv in LEVELS:
        code = lv["code"]
        items.append({"name": f"{code} Access", "type": "toggle", "img": f"images/items/{lc(code)}.png",
                      "codes": f"{lc(code)}_access"})
        for k in lv["keys"]:
            col = k.split()[0].lower()
            items.append({"name": f"{code} {k}", "type": "toggle", "img": f"images/items/key_{col}.png",
                          "codes": f"{lc(code)}_{col}"})
    for name, code in WEAPON_CODES.items():
        if code in ("pistol", "shotgun"):
            items.append({"name": name, "type": "progressive", "allow_disabled": True, "loop": False, "stages": [
                {"name": name.replace("Progressive ", ""), "img": f"images/items/{code}.png", "codes": code},
                {"name": "Dual " + name.replace("Progressive ", "") + "s", "img": f"images/items/{code}_2.png",
                 "codes": f"{code}_2", "inherit_codes": True}]})
        else:
            items.append({"name": name, "type": "toggle", "img": f"images/items/{code}.png", "codes": code})
    defaults = {"opt_weapons": True, "opt_keys": True, "opt_powerups": True, "opt_secrets": True,
                "opt_treasure_chests": True, "opt_health": False, "opt_armor": False, "opt_ammo": False}
    labels = {"opt_weapons": "Weapons", "opt_keys": "Keys", "opt_powerups": "Powerups", "opt_secrets": "Secrets",
              "opt_treasure_chests": "Treasure Chests", "opt_health": "Health", "opt_armor": "Morale (Armor)",
              "opt_ammo": "Ammo"}
    for code, on in defaults.items():
        items.append({"name": f"Show {labels[code]} checks", "type": "toggle", "img": f"images/items/{code}.png",
                      "codes": code, "initial_active_state": on})
    items.append({"name": "Auto map: follow the level you're in", "type": "toggle",
                  "img": "images/items/auto_tab.png", "codes": "auto_tab", "initial_active_state": True})
    items.append({"name": "Combat Logic", "type": "progressive", "allow_disabled": False, "loop": True, "stages": [
        {"name": "Combat logic: normal", "img": "images/items/combat_0.png", "codes": "combat,combat_normal"},
        {"name": "Combat logic: lenient", "img": "images/items/combat_1.png", "codes": "combat,combat_lenient"},
        {"name": "Combat logic: none", "img": "images/items/combat_2.png", "codes": "combat,combat_none"}]})
    items.append({"name": "Goal", "type": "progressive", "allow_disabled": False, "loop": True, "stages": [
        {"name": "Goal: bosses", "img": "images/items/goal_0.png", "codes": "goal,goal_bosses"},
        {"name": "Goal: all levels", "img": "images/items/goal_1.png", "codes": "goal,goal_all"}]})
    # hidden: which levels are in this seed (from slot_data)
    for lv in LEVELS:
        items.append({"name": f"{lv['code']} in seed", "type": "toggle", "img": f"images/items/{lc(lv['code'])}.png",
                      "codes": f"inc_{lc(lv['code'])}", "initial_active_state": True})
    wjson(f"{PACK}/items/items.json", items)


def build_maps_json(metas):
    maps = [{"name": lv["code"], "location_size": 34, "location_border_thickness": 3,
             "img": f"images/maps/{lv['code']}.png"} for lv in LEVELS]
    wjson(f"{PACK}/maps/maps.json", maps)


def build_layouts():
    tabs = []
    for ep in (1, 2, 3):
        sub = [{"title": lv["code"], "content": {"type": "map", "maps": [lv["code"]]}}
               for lv in LEVELS if lv["episode"] == ep]
        tabs.append({"title": f"Episode {ep}", "content": {"type": "tabbed", "tabs": sub}})
    wjson(f"{PACK}/layouts/tabs.json", {"tabbed_maps": {"type": "tabbed", "tabs": tabs}})

    def level_rows(ep):
        rows = []
        for lv in LEVELS:
            if lv["episode"] != ep:
                continue
            code = lv["code"]
            row = [f"{lc(code)}_access"]
            for col in ("red", "blue", "yellow"):
                row.append(f"{lc(code)}_{col}" if f"{col.title()} Key" in lv["keys"] else "")
            rows.append(row)
        return rows
    items_layouts = {
        "weapons_grid": {"type": "itemgrid", "item_margin": "2,2", "item_size": 34, "h_alignment": "center",
                         "rows": [["pistol", "shotgun", "super_shotgun"], ["assault_rifle", "hunting_rifle", "crossbow"],
                                  ["mortar", "riveter", "sword"]]},
        "settings_grid": {"type": "itemgrid", "item_margin": "2,2", "item_size": 30, "h_alignment": "center",
                          "rows": [["opt_weapons", "opt_keys", "opt_powerups", "opt_secrets", "opt_treasure_chests"],
                                   ["opt_health", "opt_armor", "opt_ammo", "combat", "goal", "auto_tab"]]},
        "levels_e1": {"type": "itemgrid", "item_margin": "1,1", "item_size": 24, "rows": level_rows(1)},
        "levels_e2": {"type": "itemgrid", "item_margin": "1,1", "item_size": 24, "rows": level_rows(2)},
        "levels_e3": {"type": "itemgrid", "item_margin": "1,1", "item_size": 24, "rows": level_rows(3)},
        "levels_all": {"type": "array", "orientation": "horizontal", "margin": "0,0", "content": [
            {"type": "group", "header": "Ep 1", "margin": "0,0,4,0", "content": {"type": "layout", "key": "levels_e1"}},
            {"type": "group", "header": "Ep 2", "margin": "0,0,4,0", "content": {"type": "layout", "key": "levels_e2"}},
            {"type": "group", "header": "Ep 3", "content": {"type": "layout", "key": "levels_e3"}}]},
        "items_panel": {"type": "array", "orientation": "vertical", "margin": "4,4", "content": [
            {"type": "group", "header": "Weapons", "content": {"type": "layout", "key": "weapons_grid"}},
            {"type": "group", "header": "Level Access & Keys", "content": {"type": "layout", "key": "levels_all"}},
            {"type": "group", "header": "Settings (auto-set from slot data)", "content": {"type": "layout", "key": "settings_grid"}}]},
    }
    # combat/goal are progressive items whose codes are their stage codes; give them a base code for the grid
    wjson(f"{PACK}/layouts/items.json", items_layouts)
    wjson(f"{PACK}/layouts/tracker.json", {"tracker_default": {
        "type": "container", "background": "#0b0a0c", "content": {
            "type": "dock", "dropshadow": True, "content": [
                {"type": "dock", "dock": "right", "content": {"type": "layout", "key": "items_panel"}},
                {"type": "layout", "key": "tabbed_maps"}]}}})
    wjson(f"{PACK}/layouts/broadcast.json", {"tracker_broadcast": {
        "type": "array", "orientation": "vertical", "background": "#000000", "content": [
            {"type": "layout", "key": "weapons_grid"}, {"type": "layout", "key": "levels_all"}]}})


def build_scripts(loc_map):
    lines = ["-- generated by build_pack.py: AP location id -> tracker section", "LOCATION_MAPPING = {"]
    for lid, path in sorted(loc_map.items()):
        lines.append(f'    [{lid}] = {{"{path}"}},')
    lines.append("}")
    open(f"{PACK}/scripts/autotracking/location_mapping.lua", "w").write("\n".join(lines) + "\n")
    lines = ["-- generated by build_pack.py: AP item id -> {code, type}", "ITEM_MAPPING = {"]
    for lv in LEVELS:
        code = lv["code"]
        lines.append(f'    [{ITEM_IDS[code + " Access"]}] = {{"{lc(code)}_access", "toggle"}},')
        for k in lv["keys"]:
            lines.append(f'    [{ITEM_IDS[code + " " + k]}] = {{"{lc(code)}_{k.split()[0].lower()}", "toggle"}},')
    for name, code in WEAPON_CODES.items():
        typ = "progressive" if code in ("pistol", "shotgun") else "toggle"
        lines.append(f'    [{ITEM_IDS[name]}] = {{"{code}", "{typ}"}},')
    lines.append("}")
    open(f"{PACK}/scripts/autotracking/item_mapping.lua", "w").write("\n".join(lines) + "\n")
    # static data for the logic
    lines = ["-- generated by build_pack.py from dusk-rando apworld/dusk/data/locations.json", "LEVEL_DATA = {"]
    for lv in LEVELS:
        num = 99 if lv["secret"] else int(lv["code"].split("M")[1])
        keys = ", ".join(f'"{k.split()[0].lower()}"' for k in lv["keys"])
        lines.append(f'    {lv["code"]} = {{name = "{lv["name"]}", episode = {lv["episode"]}, number = {num}, '
                     f'keys = {{{keys}}}}},')
    lines += ["}", "", "-- AP location id -> {level, location name}", "LOCATION_DATA = {"]
    for l in LOCS:
        lines.append(f'    [{l["id"]}] = {{"{l["level"]}", "{l["name"]}"}},')
    lines.append("}")
    open(f"{PACK}/scripts/logic/data.lua", "w").write("\n".join(lines) + "\n")


def build_manifest():
    wjson(f"{PACK}/manifest.json", {
        "name": "DUSK Archipelago",
        "game_name": "DUSK",
        "package_version": VERSION,
        "package_uid": "dusk_ap_tracker",
        "author": "FlapjackRetro",
        "min_poptracker_version": "0.25.0",
        # PopTracker checks this for updates (see versions.json / tools/package.py)
        "versions_url": VERSIONS_URL,
        "variants": {"standard": {"display_name": "Map Tracker", "flags": ["ap"]}},
    })


if __name__ == "__main__":
    only = sys.argv[1:] or None
    for sub in ("items", "locations", "maps", "layouts"):
        os.makedirs(f"{PACK}/{sub}", exist_ok=True)
    os.makedirs(f"{PACK}/scripts/autotracking", exist_ok=True)
    os.makedirs(f"{PACK}/scripts/logic", exist_ok=True)
    coords, metas = build_maps(only)
    loc_map = build_locations(coords)
    build_items()
    build_maps_json(metas)
    build_layouts()
    build_scripts(loc_map)
    build_manifest()
    print("locations mapped:", len(loc_map))
