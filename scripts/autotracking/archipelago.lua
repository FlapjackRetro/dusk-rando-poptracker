ScriptHost:LoadScript("scripts/autotracking/item_mapping.lua")
ScriptHost:LoadScript("scripts/autotracking/location_mapping.lua")

CUR_INDEX = -1
SLOT_DATA = nil

local CATEGORY_TOGGLES = {
    weapons = "opt_weapons", keys = "opt_keys", powerups = "opt_powerups", secrets = "opt_secrets",
    treasure_chests = "opt_treasure_chests", health = "opt_health", armor = "opt_armor", ammo = "opt_ammo",
}

local function dbg(fmt, ...)
    if AUTOTRACKER_ENABLE_DEBUG_LOGGING_AP then print(string.format(fmt, ...)) end
end

local function set_toggle(code, on)
    local obj = Tracker:FindObjectForCode(code)
    if obj then obj.Active = on and true or false end
end

local function set_stage(code, stage)
    local obj = Tracker:FindObjectForCode(code)
    if obj then obj.CurrentStage = stage end
end

function onClear(slot_data)
    SLOT_DATA = slot_data
    CUR_INDEX = -1
    for _, v in pairs(LOCATION_MAPPING) do
        local obj = v[1] and Tracker:FindObjectForCode(v[1])
        if obj then
            if v[1]:sub(1, 1) == "@" then
                obj.AvailableChestCount = obj.ChestCount
            else
                obj.Active = false
            end
        end
    end
    for _, v in pairs(ITEM_MAPPING) do
        local obj = v[1] and Tracker:FindObjectForCode(v[1])
        if obj then
            if v[2] == "toggle" then
                obj.Active = false
            elseif v[2] == "progressive" then
                obj.CurrentStage = 0
                obj.Active = false
            elseif v[2] == "consumable" then
                obj.AcquiredCount = 0
            end
        end
    end
    -- auto-switch the map tab to the level the player is in (the DUSK mod writes this data storage key)
    if Archipelago.PlayerNumber and Archipelago.PlayerNumber > 0 then
        LEVEL_KEY = string.format("dusk_level_%d_%d", Archipelago.TeamNumber or 0, Archipelago.PlayerNumber)
        Archipelago:SetNotify({LEVEL_KEY})
        Archipelago:Get({LEVEL_KEY})
    end
    if slot_data == nil then return end

    -- which levels are in this seed
    if slot_data["levels"] then
        local included = {}
        for _, code in ipairs(slot_data["levels"]) do included[code] = true end
        for code, _ in pairs(LEVEL_DATA) do
            set_toggle("inc_" .. code:lower(), included[code] == true)
        end
    end
    -- which pickup categories are checks
    if slot_data["categories"] then
        local on = {}
        for _, cat in ipairs(slot_data["categories"]) do on[cat] = true end
        for cat, code in pairs(CATEGORY_TOGGLES) do set_toggle(code, on[cat] == true) end
    end
    if slot_data["goal"] then
        set_stage("goal", slot_data["goal"] == "all_levels" and 1 or 0)
    end
    -- combat_logic is not in slot_data yet: set it by hand on the tracker.
    -- Stages: exorcist (0), easy (1), normal (2), unhinged (3), as the apworld's option values;
    -- lenient/none are its old names.
    if slot_data["combat_logic"] ~= nil then
        local v = slot_data["combat_logic"]
        local stage = ({exorcist = 0, easy = 1, normal = 2, unhinged = 3, lenient = 2, none = 3})[v] or tonumber(v) or 1
        set_stage("combat", stage)
    end
end

function onItem(index, item_id, item_name, player_number)
    if index <= CUR_INDEX then return end
    CUR_INDEX = index
    local v = ITEM_MAPPING[item_id]
    if not v or not v[1] then
        dbg("onItem: no mapping for %s (%s)", tostring(item_id), tostring(item_name))
        return
    end
    local obj = Tracker:FindObjectForCode(v[1])
    if not obj then
        dbg("onItem: no object for code %s", v[1])
        return
    end
    if v[2] == "toggle" then
        obj.Active = true
    elseif v[2] == "progressive" then
        if obj.Active then
            obj.CurrentStage = obj.CurrentStage + 1
        else
            obj.Active = true
        end
    elseif v[2] == "consumable" then
        obj.AcquiredCount = obj.AcquiredCount + obj.Increment
    end
end

function onLocation(location_id, location_name)
    local v = LOCATION_MAPPING[location_id]
    if not v or not v[1] then
        dbg("onLocation: no mapping for %s", tostring(location_id))
        return
    end
    local obj = Tracker:FindObjectForCode(v[1])
    if obj then
        if v[1]:sub(1, 1) == "@" then
            obj.AvailableChestCount = obj.AvailableChestCount - 1
        else
            obj.Active = true
        end
    else
        dbg("onLocation: no object for %s", v[1])
    end
end

-- ---- map auto-tab -------------------------------------------------------------------------
-- The DUSK mod stores "E2M4" (in a level), "E1"/"E2"/"E3" (episode map) or "" (menus) under
-- dusk_level_<team>_<slot>. Switch the episode tab, then the level tab. Off when "Auto map" is unticked.
local EPISODE_TAB = {E1 = "Episode 1", E2 = "Episode 2", E3 = "Episode 3"}

function switchToArea(value)
    if type(value) ~= "string" or value == "" then return end
    if not has("auto_tab") then return end
    local ep = EPISODE_TAB[value:sub(1, 2)]
    if ep then Tracker:UiHint("ActivateTab", ep) end
    if LEVEL_DATA[value] then Tracker:UiHint("ActivateTab", value) end
    dbg("auto-tab: %s", value)
end

local function onDataStorage(key, value)
    if key == LEVEL_KEY then switchToArea(value) end
end

Archipelago:AddClearHandler("clear handler", onClear)
Archipelago:AddSetReplyHandler("level handler", function(key, value, old) onDataStorage(key, value) end)
Archipelago:AddRetrievedHandler("level retrieved handler", function(key, value) onDataStorage(key, value) end)
Archipelago:AddItemHandler("item handler", onItem)
Archipelago:AddLocationHandler("location handler", onLocation)
