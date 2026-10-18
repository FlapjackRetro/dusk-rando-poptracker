-- Logic, mirroring dusk-rando's apworld/dusk/__init__.py (world_version 0.2.0):
--   * a level is in logic with "<level> Access" + enough distinct firearms (COMBAT_TABLE, combat_logic option)
--   * key logic: per-location key rules from the apworld's key_logic.py (KEY_RULES / ITEM_RULES in data.lua);
--     locations without a rule use strict key logic (all of the level's keys)
-- Levels listed in DETAILED_LOGIC (scripts/logic/regions.lua) use per-region rules instead of strict keys.

FIREARMS = {"pistol", "shotgun", "super_shotgun", "assault_rifle", "hunting_rifle", "crossbow", "mortar", "riveter"}

-- Distinct firearms required to enter a level, by episode: {from level number, count}
COMBAT_TABLE = {
    [1] = {{3, 1}, {6, 2}},
    [2] = {{2, 2}, {6, 3}},
    [3] = {{2, 3}, {6, 4}},
}

function has(code, amount)
    local count = Tracker:ProviderCountForCode(code)
    amount = tonumber(amount)
    if not amount then
        return count > 0
    end
    return count >= amount
end

-- combat_logic, as in the apworld: exorcist (testing), easy (default), normal, unhinged
local function combat_mode()
    if has("combat_exorcist") then return "exorcist" end
    if has("combat_unhinged") then return "unhinged" end
    if has("combat_normal") then return "normal" end
    return "easy"
end

-- exorcist: every level except the seed's first one needs all 10 firearm items
EXORCIST_WEAPONS = {"pistol_2", "shotgun_2", "super_shotgun", "assault_rifle", "hunting_rifle", "crossbow", "mortar",
                    "riveter"}

function exorcist_level()
    for ep = 1, 3 do
        if has("inc_e" .. ep .. "m1") then return "E" .. ep .. "M1" end
    end
    return "E1M1"
end

function firearm_count()
    local n = 0
    for _, code in ipairs(FIREARMS) do
        if has(code) then n = n + 1 end
    end
    return n
end

function firearms_needed(level)
    local lvl = LEVEL_DATA[level]
    if not lvl or not has("opt_weapons") then return 0 end
    local mode = combat_mode()
    if mode == "unhinged" or mode == "exorcist" then return 0 end  -- exorcist is handled in can_enter
    local need = 0
    for _, row in ipairs(COMBAT_TABLE[lvl.episode]) do
        if lvl.number >= row[1] then need = row[2] end
    end
    if mode == "normal" then need = math.max(0, need - 1) end
    return need
end

-- "$can_enter|E1M3"
function can_enter(level)
    if not has(level:lower() .. "_access") then return false end
    if has("opt_weapons") and combat_mode() == "exorcist" then
        if level == exorcist_level() then return true end
        for _, code in ipairs(EXORCIST_WEAPONS) do
            if not has(code) then return false end
        end
        return true
    end
    return firearm_count() >= firearms_needed(level)
end

function key_code(level, colour)
    return level:lower() .. "_" .. colour
end

function has_all_keys(level)
    if not has("opt_keys") then return true end
    for _, colour in ipairs(LEVEL_DATA[level].keys) do
        if not has(key_code(level, colour)) then return false end
    end
    return true
end

-- Requirement token: "red"/"blue"/"yellow" (this level's key; free if keys aren't randomized),
-- "@region" (another region of this level), or any item code ("mortar", "e2m4_access", ...).
local function token_ok(level, token, visiting)
    if token == "red" or token == "blue" or token == "yellow" then
        return (not has("opt_keys")) or has(key_code(level, token))
    end
    if token:sub(1, 1) == "@" then
        return region_reachable(level, token:sub(2), visiting)
    end
    return has(token)
end

-- A region's rule is a list of alternatives; each alternative is a list of tokens that must all hold.
-- {} (no alternatives) means "always reachable once inside the level".
function region_reachable(level, region, visiting)
    local spec = DETAILED_LOGIC[level]
    local rule = spec.regions[region]
    if rule == nil then
        print(string.format("DUSK logic: %s has no region '%s'", level, tostring(region)))
        return false
    end
    if #rule == 0 then return true end
    visiting = visiting or {}
    if visiting[region] then return false end
    visiting[region] = true
    for _, alt in ipairs(rule) do
        local ok = true
        for _, token in ipairs(alt) do
            if not token_ok(level, token, visiting) then ok = false break end
        end
        if ok then
            visiting[region] = nil
            return true
        end
    end
    visiting[region] = nil
    return false
end

function region_of(level, name)
    local spec = DETAILED_LOGIC[level]
    return (spec.locations and spec.locations[name]) or spec.default or "start"
end

-- "$check|<AP location id>"  (level access is already required by the parent location)
function check(id)
    local d = LOCATION_DATA[tonumber(id)]
    if not d then return false end
    local level, name = d[1], d[2]
    if DETAILED_LOGIC[level] then
        return region_reachable(level, region_of(level, name))
    end
    return keys_ok(level, name) and items_ok(name)
end

-- Key rule from the apworld (KEY_RULES in data.lua): the listed colours, the level's "*" rule, or all keys.
function keys_ok(level, name)
    if not has("opt_keys") then return true end
    local rules = KEY_RULES[level]
    local rule = rules and (rules[name] or rules["*"])
    if rule == nil then return has_all_keys(level) end
    for _, colour in ipairs(rule) do
        if not has(key_code(level, colour)) then return false end
    end
    return true
end

-- Extra items a location needs (ITEM_RULES in data.lua); only when weapons are randomized.
function items_ok(name)
    local items = ITEM_RULES[name]
    if not items or not has("opt_weapons") then return true end
    for _, code in ipairs(items) do
        if not has(code) then return false end
    end
    return true
end
